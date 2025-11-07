"""Backtest CLI runner."""

import argparse
import sys
from pathlib import Path

from .utils import load_config, setup_logging, get_market_config, list_available_markets
from .bt_engine import BacktestEngine
from .bt_reports import BacktestReporter


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run RSI-2 backtest on historical candle data'
    )

    parser.add_argument(
        '--data-path',
        type=str,
        required=True,
        help='Path to CSV file or directory containing CSV files'
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
        help='Market to backtest (e.g., US500, GERMANY40). If not specified, uses default_market from config'
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
        '--sl',
        type=float,
        default=None,
        help='Stop loss in points (default from config)'
    )

    parser.add_argument(
        '--spread',
        type=float,
        default=None,
        help='Spread assumption in points (default from config)'
    )

    parser.add_argument(
        '--tz',
        type=str,
        default=None,
        help='Timezone (default from market config)'
    )

    parser.add_argument(
        '--open',
        type=str,
        default=None,
        help='Session open time HH:MM (default from config)'
    )

    parser.add_argument(
        '--close',
        type=str,
        default=None,
        help='Session close time HH:MM (default from config)'
    )

    parser.add_argument(
        '--skip-first',
        type=int,
        default=None,
        help='Minutes to skip at session start (default from config)'
    )

    parser.add_argument(
        '--out',
        type=str,
        default='reports/backtest',
        help='Output directory for reports (default: reports/backtest)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to config file (default: config.yaml)'
    )

    parser.add_argument(
        '--show-trades',
        action='store_true',
        help='Print detailed trade information'
    )

    return parser.parse_args()


def main():
    """Main backtest entry point."""
    args = parse_args()

    # Load configuration
    try:
        base_config = load_config(args.config)

        # Get market-specific config
        config = get_market_config(base_config, args.market)

        # Override config with CLI arguments
        if args.rsi_period is not None:
            config['rsi_period'] = args.rsi_period
        if args.timeframe is not None:
            config['timeframe_sec'] = args.timeframe
        if args.sl is not None:
            config['stop_loss_pts'] = args.sl
        if args.spread is not None:
            config['spread_assumption_pts'] = args.spread
        if args.tz is not None:
            config['tz'] = args.tz
        if args.open is not None:
            config['session_open'] = args.open
        if args.close is not None:
            config['session_close'] = args.close
        if args.skip_first is not None:
            config['no_trade_first_minutes'] = args.skip_first

        # Get take profit: CLI overrides config
        tp_pts = args.tp if args.tp is not None else base_config.get('take_profits_pts')
        if tp_pts is None:
            print("Error: No take profit specified. Use --tp or set take_profits_pts in config.yaml")
            sys.exit(1)

    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Setup logging
    logger = setup_logging(config.get('log_level', 'INFO'))

    # Print configuration summary
    market_name = args.market if args.market else base_config.get('default_market', 'US500')
    logger.info(f"Backtest market: {market_name} ({config.get('symbol', 'Unknown')})")
    logger.info(f"Timeframe: {config.get('timeframe_sec', 1800)}s")
    logger.info(f"RSI period: {config.get('rsi_period', 2)}, oversold threshold: {config.get('oversold', 3.0)}")
    logger.info(f"Timezone: {config.get('tz', 'Unknown')}")
    logger.info(f"Session: {config.get('session_open', 'Unknown')} - {config.get('session_close', 'Unknown')}")
    logger.info(f"Starting backtest with TP={tp_pts} pts, SL={config['stop_loss_pts']} pts, Spread={config.get('spread_assumption_pts', 0.6)} pts")
    logger.info(f"Data path: {args.data_path}")
    logger.info(f"Output directory: {args.out}")

    # Verify data path exists
    data_path = Path(args.data_path)
    if not data_path.exists():
        logger.error(f"Data path does not exist: {args.data_path}")
        sys.exit(1)

    try:
        # Initialize engine and reporter
        engine = BacktestEngine(config)
        reporter = BacktestReporter(args.out)

        # Load data
        logger.info("Loading historical data...")
        df = engine.load_data(args.data_path)
        logger.info(f"Loaded {len(df)} bars from {df['timestamp'].min()} to {df['timestamp'].max()}")

        # Run backtest
        logger.info(f"Running backtest with TP={tp_pts} pts...")
        trades = engine.run_backtest(df, tp_pts)

        logger.info(f"Backtest complete. Total trades: {len(trades)}")

        # Show detailed trades if requested
        if args.show_trades and trades:
            reporter.print_trades_detail(trades)

        # Generate reports
        reporter.generate_reports(trades, tp_pts, config.get('stop_loss_pts'))

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
