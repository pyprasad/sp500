"""Run tick-level backtest using tick data for realistic simulation."""

import argparse
import yaml
from pathlib import Path
import logging

from .tick_backtest_engine import TickBacktestEngine
from .bt_reports import BacktestReporter


def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def load_config(config_path: str, market: str = None) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml
        market: Market name (e.g., 'GERMANY40')

    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Merge market-specific config if specified
    if market:
        if 'markets' not in config or market not in config['markets']:
            raise ValueError(f"Market '{market}' not found in config")

        market_config = config['markets'][market]
        config.update(market_config)
        config['market_name'] = market

    return config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run tick-level backtest for RSI-2 strategy'
    )

    parser.add_argument(
        '--tick-data',
        type=str,
        required=True,
        help='Path to tick data CSV file (e.g., dax_2024_full_scaled.csv)'
    )

    parser.add_argument(
        '--tp',
        type=float,
        required=True,
        help='Take profit in points (e.g., 40)'
    )

    parser.add_argument(
        '--market',
        type=str,
        default='GERMANY40',
        help='Market to backtest (default: GERMANY40)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to config file (default: config.yaml)'
    )

    parser.add_argument(
        '--out',
        type=str,
        default='reports/tick_backtest',
        help='Output directory for reports (default: reports/tick_backtest)'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("TICK-LEVEL BACKTEST - RSI-2 Strategy")
    logger.info("=" * 70)
    logger.info(f"Tick Data: {args.tick_data}")
    logger.info(f"Market: {args.market}")
    logger.info(f"TP: {args.tp} pts")
    logger.info("=" * 70)

    # Load configuration
    config = load_config(args.config, args.market)

    # Initialize engine
    engine = TickBacktestEngine(config)

    # Load tick data
    logger.info("Loading tick data...")
    ticks_df = engine.load_tick_data(args.tick_data)

    # Build candles from ticks
    logger.info("Building candles from ticks...")
    timeframe_minutes = config.get('timeframe_sec', 1800) // 60
    candles_df = engine.build_candles_from_ticks(ticks_df, timeframe_minutes)

    # Filter to session hours
    logger.info("Filtering to session hours...")
    candles_df = engine.filter_session_bars(candles_df)

    # Run tick backtest
    logger.info("Running tick-level backtest...")
    trades = engine.run_tick_backtest(ticks_df, candles_df, args.tp)

    # Generate reports
    logger.info("Generating reports...")
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    reporter = BacktestReporter(output_dir)
    reporter.generate_reports(trades, args.tp)

    logger.info("=" * 70)
    logger.info("TICK BACKTEST COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Reports saved to: {output_dir}")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()
