"""Live trading CLI runner."""

import argparse
import sys
import signal
import time
from datetime import datetime
from pathlib import Path

from .utils import load_config, setup_logging, get_market_config, list_available_markets
from .ig_auth import IGAuth
from .ig_stream import IGStream
from .candle_builder import CandleBuilder
from .strategy import RSI2Strategy
from .broker import IGBroker
from .risk import RiskManager
from .trade_log import TradeLogger


class LiveTrader:
    """Main live trading orchestrator."""

    def __init__(self, config: dict, tp_pts: float):
        """
        Initialize live trader.

        Args:
            config: Configuration dictionary
            tp_pts: Take profit in points
        """
        self.config = config
        self.tp_pts = tp_pts
        self.running = False

        # Setup logging
        log_file = Path("logs") / f"runtime_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.logger = setup_logging(config.get('log_level', 'INFO'), str(log_file))

        self.logger.info(f"Initializing live trader with TP={tp_pts} pts")

        # Initialize components
        self.auth = IGAuth()
        self.strategy = RSI2Strategy(config)
        self.risk_manager = RiskManager(config)
        self.trade_logger = TradeLogger()

        self.broker = None
        self.stream = None
        self.candle_builder = None

        # Current market data
        self.current_bid = None
        self.current_ask = None

        # Deal tracking
        self.current_deal_ref = None
        self.last_trading_date = None

    def start(self):
        """Start live trading."""
        # Authenticate
        if not self.auth.authenticate():
            self.logger.error("Authentication failed")
            sys.exit(1)

        # Initialize broker
        self.broker = IGBroker(self.auth, self.config)

        # Initialize candle builder
        timeframe_sec = self.config.get('timeframe_sec', 1800)
        self.candle_builder = CandleBuilder(timeframe_sec)
        self.candle_builder.set_candle_callback(self.on_candle_complete)

        # Start tick logging
        tick_file = Path("data/ticks") / f"ticks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.candle_builder.start_tick_logging(str(tick_file))

        # Initialize streaming
        self.stream = IGStream(
            epic=self.config.get('epic'),
            account_id=self.auth.account_id,
            cst=self.auth.cst_token,
            x_security=self.auth.x_security_token,
            ls_endpoint=self.auth.lightstreamer_endpoint
        )
        self.stream.subscribe_ticks(self.on_tick)

        # Connect to stream
        self.stream.connect()

        self.logger.info("Live trading started")
        self.running = True

        # Main loop
        last_heartbeat = time.time()
        tick_count_last = 0
        last_tick_time = time.time()

        try:
            while self.running:
                time.sleep(1)

                # Check if ticks are still flowing
                tick_count = getattr(self.candle_builder, 'tick_count', 0)
                if tick_count > tick_count_last:
                    last_tick_time = time.time()

                # Warn if no ticks for 60 seconds (after initial connection)
                now = time.time()
                if tick_count > 0 and (now - last_tick_time) > 60:
                    self.logger.warning(f"No ticks received for {int(now - last_tick_time)} seconds - check market hours or connection")
                    last_tick_time = now  # Reset to avoid repeated warnings

                # Heartbeat every 30 seconds to show system is alive
                if now - last_heartbeat >= 30:
                    ticks_received = tick_count - tick_count_last
                    tick_count_last = tick_count

                    status_msg = f"Status: Ticks={tick_count} (+{ticks_received}/30s)"
                    if self.current_bid and self.current_ask:
                        status_msg += f" | Price: BID={self.current_bid:.2f} ASK={self.current_ask:.2f}"

                    rsi = self.strategy.get_current_rsi()
                    if rsi:
                        status_msg += f" | RSI={rsi:.2f}"

                    if self.strategy.has_position():
                        pos = self.strategy.get_position()
                        status_msg += f" | Position: {pos['entry_price']:.2f}"
                    else:
                        status_msg += " | Position: None"

                    self.logger.info(status_msg)
                    last_heartbeat = now

                # Check for position exits
                if self.strategy.has_position() and self.current_bid:
                    self._check_position_exit()

                # Check for EOD exit
                if self.strategy.has_position():
                    if self.strategy.check_eod_exit(datetime.now()):
                        self.logger.info("EOD - closing position")
                        self._close_position(self.current_bid, 'EOD')

        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")

        finally:
            self.stop()

    def stop(self):
        """Stop live trading."""
        self.running = False

        # Close any open position
        if self.strategy.has_position():
            self.logger.warning("Closing position at shutdown")
            if self.current_bid:
                self._close_position(self.current_bid, 'SHUTDOWN')

        # Disconnect stream
        if self.stream:
            self.stream.disconnect()

        # Stop tick logging
        if self.candle_builder:
            self.candle_builder.force_complete_candle()
            self.candle_builder.stop_tick_logging()

        # Logout
        self.auth.logout()

        # Print summary
        self.trade_logger.print_summary()

        self.logger.info("Live trading stopped")

    def on_tick(self, bid: float, ask: float, timestamp: str):
        """
        Handle incoming tick.

        Args:
            bid: Bid price
            ask: Ask price
            timestamp: Tick timestamp
        """
        self.current_bid = bid
        self.current_ask = ask

        # Process tick through candle builder
        self.candle_builder.process_tick(bid, ask, timestamp)

    def on_candle_complete(self, candle: dict):
        """
        Handle completed candle.

        Args:
            candle: Candle dictionary
        """
        self.logger.info(f"New candle: {candle['timestamp']} "
                        f"O:{candle['open']:.2f} H:{candle['high']:.2f} "
                        f"L:{candle['low']:.2f} C:{candle['close']:.2f}")

        # Add candle to strategy
        self.strategy.add_candle(candle)

        # Compute indicators
        self.strategy.compute_indicators()

        # Get current RSI
        rsi = self.strategy.get_current_rsi()
        if rsi:
            self.logger.info(f"RSI(2): {rsi:.2f}")

        # Check for new trading day
        current_date = self.strategy.session_clock.get_trading_date(candle['timestamp'])
        if self.last_trading_date is None or current_date != self.last_trading_date:
            self.logger.info(f"New trading day: {current_date}")
            self.strategy.reset_daily_state()
            self.last_trading_date = current_date

        # Check for entry signal
        if not self.strategy.has_position():
            if self.strategy.check_entry_signal(candle['timestamp']):
                self._open_position()

    def _open_position(self):
        """Open new position."""
        if not self.current_ask or not self.current_bid:
            self.logger.warning("No current prices available")
            return

        # Calculate entry price (ask)
        entry_price = self.risk_manager.calculate_entry_price(
            self.current_bid, self.current_ask, 'BUY'
        )

        # Calculate exit levels
        levels = self.risk_manager.calculate_exit_levels(
            entry_price, self.tp_pts, 'BUY'
        )

        # Open position via broker
        deal_ref = self.broker.open_position(
            direction='BUY',
            entry_price=entry_price,
            stop_level=levels['stop_level'],
            limit_level=levels['limit_level']
        )

        if deal_ref:
            self.current_deal_ref = deal_ref

            # Update strategy state
            self.strategy.open_position(
                entry_price=entry_price,
                tp_pts=self.tp_pts,
                sl_pts=self.config.get('stop_loss_pts', 2.0),
                timestamp=datetime.now()
            )

    def _check_position_exit(self):
        """Check if position should be exited."""
        position = self.strategy.get_position()
        if not position:
            return

        should_exit, reason = self.risk_manager.check_exit(
            position, self.current_bid, self.current_ask
        )

        if should_exit:
            self._close_position(self.current_bid, reason)

    def _close_position(self, exit_price: float, reason: str):
        """Close current position."""
        if not self.strategy.has_position():
            return

        # Close via strategy
        trade = self.strategy.close_position(
            exit_price=exit_price,
            exit_reason=reason,
            timestamp=datetime.now()
        )

        # Log trade
        self.trade_logger.log_trade(trade)

        # Close via broker (if not dry run)
        if self.current_deal_ref and not self.config.get('dry_run', True):
            self.broker.close_position(
                deal_id=self.current_deal_ref,
                direction='SELL',
                size=self.config.get('size_gbp_per_point', 1.0)
            )

        self.current_deal_ref = None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run RSI-2 live trading on IG Demo'
    )

    parser.add_argument(
        '--tp',
        type=float,
        required=True,
        help='Take profit in points (e.g., 5 or 10)'
    )

    parser.add_argument(
        '--market',
        type=str,
        default=None,
        help='Market to trade (e.g., US500, GERMANY40). If not specified, uses default_market from config'
    )

    parser.add_argument(
        '--rsi-period',
        type=int,
        default=None,
        help='RSI period (default from config)'
    )

    parser.add_argument(
        '--timeframe',
        type=int,
        default=None,
        help='Candle timeframe in seconds (default from config)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to config file (default: config.yaml)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Load configuration
    try:
        base_config = load_config(args.config)

        # Get market-specific config
        config = get_market_config(base_config, args.market)

        # Apply CLI overrides
        if args.rsi_period is not None:
            config['rsi_period'] = args.rsi_period
        if args.timeframe is not None:
            config['timeframe_sec'] = args.timeframe

        # Print selected market info
        market_name = args.market if args.market else base_config.get('default_market', 'US500')
        print(f"Trading market: {market_name} ({config.get('symbol', 'Unknown')})")
        print(f"EPIC: {config.get('epic', 'Unknown')}")
        print(f"Timeframe: {config.get('timeframe_sec', 1800)}s")
        print(f"RSI period: {config.get('rsi_period', 2)}")
        print(f"Timezone: {config.get('tz', 'Unknown')}")
        print(f"Session: {config.get('session_open', 'Unknown')} - {config.get('session_close', 'Unknown')}")
        print("")

    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Create trader
    trader = LiveTrader(config, args.tp)

    # Setup signal handlers
    def signal_handler(sig, frame):
        trader.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start trading
    trader.start()


if __name__ == '__main__':
    main()
