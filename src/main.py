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
from .ig_historical import IGHistoricalData
from .candle_builder import CandleBuilder
from .strategy import RSI2Strategy
from .broker import IGBroker
from .risk import RiskManager
from .trade_log import TradeLogger
from .trade_state import TradeState
from .trailing_stop_manager import TrailingStopManager


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

        # Trade state persistence (per-market state file from config)
        state_file = config.get('state_file', 'data/state/trade_state.json')
        self.trade_state = TradeState(state_file)

        # Trailing stop manager (if enabled)
        self.trailing_manager = TrailingStopManager(config) if config.get('use_trailing_stop', False) else None
        if self.trailing_manager:
            self.logger.info("Trailing stop manager enabled")

        self.broker = None
        self.stream = None
        self.candle_builder = None

        # Current market data
        self.current_bid = None
        self.current_ask = None

        # Deal tracking
        self.current_deal_ref = None
        self.current_deal_id = None
        self.last_trading_date = None

        # Rate limiting for SL updates (prevent API spam)
        self.last_sl_update_time = 0
        self.min_sl_update_interval = 2.0  # Minimum 2 seconds between updates

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

        # Pre-load historical candles for accurate RSI
        self._preload_historical_candles()

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

        # Subscribe to position updates (for instant close notifications)
        if self.trailing_manager:
            self.stream.subscribe_positions(self.on_position_update)

        # Connect to stream
        self.stream.connect()

        # Position reconciliation (check for saved position from previous crash)
        self._reconcile_position()

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

                # Process trailing stop (if enabled and position open)
                if self.trailing_manager and self.trailing_manager.has_position() and self.current_bid:
                    should_update, new_sl, _ = self.trailing_manager.on_tick(self.current_bid)
                    if should_update and new_sl:
                        self._update_stop_loss(new_sl)

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

    def _preload_historical_candles(self):
        """Pre-load historical candles from IG API for accurate RSI calculation."""
        preload_candles = self.config.get('preload_candles', 50)

        if preload_candles <= 0:
            self.logger.info("Historical candle pre-loading disabled (preload_candles=0)")
            return

        try:
            self.logger.info(f"Pre-loading {preload_candles} historical candles...")

            # Initialize historical data fetcher
            historical = IGHistoricalData(self.auth)

            # Get resolution from timeframe
            timeframe_sec = self.config.get('timeframe_sec', 1800)
            resolution = historical.get_resolution_from_timeframe(timeframe_sec)

            # Fetch historical candles
            candles = historical.fetch_historical_candles(
                epic=self.config.get('epic'),
                resolution=resolution,
                num_points=preload_candles,
                market_name=self.config.get('market_name')
            )

            if not candles:
                self.logger.warning("Failed to fetch historical candles, starting with cold RSI")
                self.logger.warning("RSI will warm up over time as candles accumulate")
                return

            # Load candles into strategy
            self.strategy.load_historical_candles(candles)

            self.logger.info(f"✓ Successfully pre-loaded {len(candles)} historical candles")
            self.logger.info(f"Historical data range: {candles[0]['timestamp']} to {candles[-1]['timestamp']}")

        except Exception as e:
            self.logger.error(f"Error pre-loading historical candles: {e}", exc_info=True)
            self.logger.warning("Starting with cold RSI - will warm up over time")

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
            # Note: deal_id is different from deal_ref. We'll get deal_id from CONFIRMS stream or query

            # Update strategy state
            self.strategy.open_position(
                entry_price=entry_price,
                tp_pts=self.tp_pts,
                sl_pts=self.config.get('stop_loss_pts', 2.0),
                timestamp=datetime.now()
            )

            # Save trade state for crash recovery
            position_state = {
                'deal_id': deal_ref,  # Will be updated with real deal_id from stream
                'deal_ref': deal_ref,
                'entry_price': entry_price,
                'tp_level': levels['limit_level'],
                'sl_level': levels['stop_level'],
                'entry_time': datetime.now().isoformat(),
                'direction': 'BUY'
            }
            self.trade_state.save_position(position_state)

            # Initialize trailing stop manager (if enabled)
            if self.trailing_manager:
                self.trailing_manager.on_position_opened(
                    entry_price=entry_price,
                    tp_level=levels['limit_level'],
                    sl_level=levels['stop_level'],
                    deal_id=deal_ref
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

        # Clear trade state
        self.trade_state.clear_position()

        # Reset trailing stop manager
        if self.trailing_manager:
            self.trailing_manager.on_position_closed()

        self.current_deal_ref = None
        self.current_deal_id = None

    def _reconcile_position(self):
        """
        Reconcile position on startup (crash recovery).

        Checks if saved position still exists on IG, restores tracking if yes.
        """
        saved_position = self.trade_state.load_position()
        if not saved_position:
            return

        deal_id = saved_position.get('deal_id')

        # Query IG to verify position still exists
        live_position = self.broker.get_position_by_deal_id(deal_id)

        if not live_position:
            self.logger.warning("Saved position no longer exists on IG - clearing stale state")
            self.trade_state.clear_position()
            return

        # Position exists - restore strategy and trailing manager
        entry_price = saved_position['entry_price']
        tp_level = saved_position['tp_level']
        sl_level = saved_position['sl_level']

        self.logger.warning("Restoring position tracking...")

        # Restore strategy state
        self.strategy.open_position(
            entry_price=entry_price,
            tp_pts=self.tp_pts,
            sl_pts=self.config.get('stop_loss_pts', 2.0),
            timestamp=datetime.now()
        )

        self.current_deal_id = deal_id
        self.current_deal_ref = saved_position.get('deal_ref', deal_id)

        # Restore trailing manager (if enabled)
        if self.trailing_manager:
            # Get current price for restoration
            current_price = self.current_bid
            if not current_price:
                # Try to fetch from broker if not available yet
                price_data = self.broker.get_current_price()
                if price_data:
                    current_price = price_data['bid']
                else:
                    # Fall back to entry price if we can't get current price
                    current_price = entry_price
                    self.logger.warning("Using entry price for trailing restoration (current price unavailable)")

            self.trailing_manager.restore_position(saved_position, current_price)

        self.logger.warning("✓ Position restored successfully")

    def _update_stop_loss(self, new_sl_level: float):
        """
        Update stop loss level via broker API.

        Args:
            new_sl_level: New stop loss level
        """
        if not self.current_deal_id:
            self.logger.warning("Cannot update SL: no deal_id available")
            return

        # Rate limiting: prevent API spam
        now = time.time()
        if (now - self.last_sl_update_time) < self.min_sl_update_interval:
            self.logger.debug(f"Skipping SL update (rate limited): {new_sl_level:.2f}")
            return

        success = self.broker.update_stop_level(self.current_deal_id, new_sl_level)

        if success:
            self.logger.info(f"✓ Trailing SL updated: {new_sl_level:.2f}")
            self.last_sl_update_time = now
        else:
            self.logger.error(f"✗ Failed to update trailing SL to {new_sl_level:.2f}")

    def on_position_update(self, update_type: str, data: str):
        """
        Handle position update from streaming API.

        Args:
            update_type: Type of update (CONFIRMS, OPU, WOU)
            data: Update data (JSON string)
        """
        try:
            import json
            update_dict = json.loads(data)

            # Handle deal confirmation (get real deal_id)
            if update_type == 'CONFIRMS':
                deal_ref = update_dict.get('dealReference')
                deal_id = update_dict.get('dealId')
                status = update_dict.get('dealStatus')

                if deal_ref == self.current_deal_ref:
                    if status == 'ACCEPTED':
                        self.current_deal_id = deal_id
                        self.logger.info(f"Deal confirmed: deal_id={deal_id}")
                    else:
                        self.logger.error(f"Deal rejected: {status} - {update_dict.get('reason', 'Unknown')}")

            # Handle position update (OPU) - check for closes
            elif update_type == 'OPU':
                deal_id = update_dict.get('dealId')
                status = update_dict.get('status')

                if deal_id == self.current_deal_id and status in ['DELETED', 'CLOSED']:
                    self.logger.info(f"Position closed via stream: deal_id={deal_id}, status={status}")
                    # Position closed by IG (TP/SL hit) - update local state
                    if self.strategy.has_position():
                        exit_price = update_dict.get('level', self.current_bid)
                        self._close_position(exit_price, 'BROKER_CLOSE')

        except Exception as e:
            self.logger.error(f"Error processing position update: {e}", exc_info=True)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run RSI-2 live trading on IG Demo'
    )

    parser.add_argument(
        '--tp',
        type=float,
        default=None,
        help='Take profit in points (e.g., 5 or 10). If not specified, uses take_profits_pts from config'
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

        # Get take profit: CLI overrides config
        tp_pts = args.tp if args.tp is not None else base_config.get('take_profits_pts')
        if tp_pts is None:
            print("Error: No take profit specified. Use --tp or set take_profits_pts in config.yaml")
            sys.exit(1)

        # Get market name
        market_name = args.market if args.market else base_config.get('default_market', 'US500')

        # Add market name to config for historical data naming
        config['market_name'] = market_name

        # Print selected market info
        print(f"Trading market: {market_name} ({config.get('symbol', 'Unknown')})")
        print(f"EPIC: {config.get('epic', 'Unknown')}")
        print(f"Timeframe: {config.get('timeframe_sec', 1800)}s")
        print(f"RSI period: {config.get('rsi_period', 2)}")
        print(f"Timezone: {config.get('tz', 'Unknown')}")
        print(f"Session: {config.get('session_open', 'Unknown')} - {config.get('session_close', 'Unknown')}")
        print(f"Take Profit: {tp_pts} pts")
        print("")

    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Create trader
    trader = LiveTrader(config, tp_pts)

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
