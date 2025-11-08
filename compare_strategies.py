#!/usr/bin/env python3
"""
Strategy Comparison Script: EOD Exit vs Overnight Holds

Runs backtest with both force_eod_exit=true and force_eod_exit=false,
then displays a clean side-by-side comparison.

Usage:
    python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40
    python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --tp 40
    python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --output report.txt
"""

import argparse
import sys
import pandas as pd
from pathlib import Path
import tempfile
import shutil

# Import existing backtest components
from src.utils import load_config, get_market_config
from src.bt_engine import BacktestEngine
from src.bt_reports import BacktestReporter


def run_single_backtest(config, tp_pts, force_eod_exit, data_path):
    """
    Run a single backtest with specified force_eod_exit setting.

    Args:
        config: Configuration dictionary
        tp_pts: Take profit in points
        force_eod_exit: True/False for EOD exit policy
        data_path: Path to historical data

    Returns:
        Tuple of (trades_df, summary_dict)
    """
    # Create a copy of config and modify force_eod_exit
    test_config = config.copy()
    test_config['force_eod_exit'] = force_eod_exit

    # Initialize engine and reporter
    engine = BacktestEngine(test_config)
    reporter = BacktestReporter()

    # Load data
    df = engine.load_data(data_path)
    df = engine.filter_session_bars(df)

    # Run backtest
    trades = engine.run_backtest(df, tp_pts)

    # Convert to DataFrame
    trades_df = pd.DataFrame(trades)

    if trades_df.empty:
        return None, None

    # Generate summary
    summary = reporter._generate_summary(trades_df)

    return trades_df, summary


def format_number(value, decimals=2, prefix="", suffix=""):
    """Format number with proper sign and decimals."""
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}{suffix}".rjust(15)


def format_diff(val1, val2, decimals=2, suffix="", is_percentage=False):
    """Calculate and format difference between two values."""
    if val1 is None or val2 is None:
        return "N/A".rjust(18)

    diff = val2 - val1

    if is_percentage and val1 != 0:
        pct_change = (diff / abs(val1)) * 100
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.{decimals}f} ({sign}{pct_change:.0f}%)".rjust(18)
    else:
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.{decimals}f}{suffix}".rjust(18)


def print_comparison(eod_summary, overnight_summary, eod_trades, overnight_trades, output_file=None):
    """
    Print side-by-side comparison of two strategies.

    Args:
        eod_summary: Summary dict for EOD exit strategy
        overnight_summary: Summary dict for overnight strategy
        eod_trades: Trades DataFrame for EOD strategy
        overnight_trades: Trades DataFrame for overnight strategy
        output_file: Optional file path to save output
    """
    lines = []

    def add_line(text):
        lines.append(text)
        print(text)

    add_line("=" * 100)
    add_line("STRATEGY COMPARISON: EOD EXIT vs OVERNIGHT HOLDS")
    add_line("=" * 100)
    add_line("")

    # Header info
    if not eod_trades.empty:
        start_date = eod_trades['datetime_open'].min()
        end_date = eod_trades['datetime_close'].max()
        add_line(f"Data Period: {start_date} to {end_date}")
    add_line(f"Total Bars: {eod_summary.get('trades', 0)} trades")
    add_line("")
    add_line("=" * 100)
    add_line("")

    # Table header
    add_line(f"{'Metric':<35} {'EOD Exit (true)':>18} {'Overnight (false)':>18} {'Difference':>18}")
    add_line("-" * 100)

    # Performance Metrics
    add_line(f"{'PERFORMANCE':<35}")
    add_line(f"{'Total P&L (NET)':<35} {format_number(eod_summary['total_pts'], 2, suffix=' pts')} "
             f"{format_number(overnight_summary['total_pts'], 2, suffix=' pts')} "
             f"{format_diff(eod_summary['total_pts'], overnight_summary['total_pts'], 2, ' pts', True)}")

    add_line(f"{'Return %':<35} {format_number(eod_summary['return_pct'], 2, suffix='%')} "
             f"{format_number(overnight_summary['return_pct'], 2, suffix='%')} "
             f"{format_diff(eod_summary['return_pct'], overnight_summary['return_pct'], 2, '%')}")

    eod_balance_str = f"£{eod_summary['final_balance']:,.2f}"
    overnight_balance_str = f"£{overnight_summary['final_balance']:,.2f}"
    balance_diff = format_diff(eod_summary['final_balance'], overnight_summary['final_balance'], 2, '', False)
    add_line(f"{'Final Balance':<35} {eod_balance_str:>18} {overnight_balance_str:>18} {balance_diff}")

    add_line("")

    # Overnight Metrics
    add_line(f"{'OVERNIGHT METRICS':<35}")

    eod_overnight_charges = eod_summary.get('total_overnight_charges', 0)
    overnight_charges = overnight_summary.get('total_overnight_charges', 0)
    add_line(f"{'Overnight Charges':<35} {format_number(eod_overnight_charges, 2, suffix=' pts')} "
             f"{format_number(overnight_charges, 2, suffix=' pts')} "
             f"{format_diff(eod_overnight_charges, overnight_charges, 2, ' pts')}")

    eod_positions_overnight = eod_summary.get('positions_held_overnight', 0)
    overnight_positions = overnight_summary.get('positions_held_overnight', 0)
    eod_pct = (eod_positions_overnight / eod_summary['trades'] * 100) if eod_summary['trades'] > 0 else 0
    overnight_pct = (overnight_positions / overnight_summary['trades'] * 100) if overnight_summary['trades'] > 0 else 0

    add_line(f"{'Positions Held Overnight':<35} {f'{eod_positions_overnight} ({eod_pct:.1f}%)':>18} "
             f"{f'{overnight_positions} ({overnight_pct:.1f}%)':>18} "
             f"{format_diff(eod_positions_overnight, overnight_positions, 0, '')}")

    add_line(f"{'Avg Days Held':<35} {format_number(eod_summary.get('avg_days_held', 0), 2)} "
             f"{format_number(overnight_summary.get('avg_days_held', 0), 2)} "
             f"{format_diff(eod_summary.get('avg_days_held', 0), overnight_summary.get('avg_days_held', 0), 2)}")

    add_line(f"{'Avg Bars Held':<35} {format_number(eod_summary['avg_bars_held'], 1)} "
             f"{format_number(overnight_summary['avg_bars_held'], 1)} "
             f"{format_diff(eod_summary['avg_bars_held'], overnight_summary['avg_bars_held'], 1)}")

    add_line("")

    # Risk Metrics
    add_line(f"{'RISK METRICS':<35}")
    add_line(f"{'Max Drawdown':<35} {format_number(eod_summary['max_drawdown_pts'], 2, suffix=' pts')} "
             f"{format_number(overnight_summary['max_drawdown_pts'], 2, suffix=' pts')} "
             f"{format_diff(eod_summary['max_drawdown_pts'], overnight_summary['max_drawdown_pts'], 2, ' pts')}")

    add_line(f"{'Win Rate':<35} {format_number(eod_summary['win_rate'], 2, suffix='%')} "
             f"{format_number(overnight_summary['win_rate'], 2, suffix='%')} "
             f"{format_diff(eod_summary['win_rate'], overnight_summary['win_rate'], 2, '%')}")

    add_line("")

    # Exit Reasons
    add_line(f"{'EXIT REASONS':<35}")

    # Trailing SL Exits
    eod_trailing = f"{eod_summary['trailing_sl_exits']} ({eod_summary['trailing_sl_pnl_pts']:+.0f} pts)"
    overnight_trailing = f"{overnight_summary['trailing_sl_exits']} ({overnight_summary['trailing_sl_pnl_pts']:+.0f} pts)"
    trailing_diff = format_diff(eod_summary['trailing_sl_exits'], overnight_summary['trailing_sl_exits'], 0)
    add_line(f"{'Trailing SL Exits':<35} {eod_trailing:>18} {overnight_trailing:>18} {trailing_diff}")

    # SL Exits
    eod_sl = f"{eod_summary['sl_exits']} ({eod_summary['sl_pnl_pts']:+.0f} pts)"
    overnight_sl = f"{overnight_summary['sl_exits']} ({overnight_summary['sl_pnl_pts']:+.0f} pts)"
    sl_diff = format_diff(eod_summary['sl_exits'], overnight_summary['sl_exits'], 0)
    add_line(f"{'SL Exits':<35} {eod_sl:>18} {overnight_sl:>18} {sl_diff}")

    # EOD Exits
    eod_eod = f"{eod_summary['eod_exits']} ({eod_summary['eod_pnl_pts']:+.0f} pts)"
    overnight_eod = f"{overnight_summary['eod_exits']} ({overnight_summary['eod_pnl_pts']:+.0f} pts)"
    eod_diff = format_diff(eod_summary['eod_exits'], overnight_summary['eod_exits'], 0)
    add_line(f"{'EOD Exits':<35} {eod_eod:>18} {overnight_eod:>18} {eod_diff}")

    add_line("")
    add_line("=" * 100)

    # Analysis
    pnl_diff = overnight_summary['total_pts'] - eod_summary['total_pts']
    pnl_pct_change = (pnl_diff / abs(eod_summary['total_pts']) * 100) if eod_summary['total_pts'] != 0 else 0

    add_line("")
    add_line("ANALYSIS:")
    add_line("-" * 100)

    if pnl_diff > 0:
        roi = (pnl_diff / overnight_charges) if overnight_charges > 0 else 0
        add_line(f"✅ Overnight strategy is {pnl_pct_change:+.1f}% MORE PROFITABLE ({pnl_diff:+.2f} pts)")
        add_line(f"   - Extra profit: {pnl_diff:+.2f} pts")
        add_line(f"   - Overnight charges: {overnight_charges:.2f} pts")
        if overnight_charges > 0:
            add_line(f"   - ROI on overnight costs: {roi:.1f}x (gained {roi:.1f} pts for every 1 pt spent)")
    else:
        add_line(f"❌ EOD strategy is {abs(pnl_pct_change):.1f}% BETTER ({abs(pnl_diff):.2f} pts)")
        add_line(f"   - Overnight charges hurt performance: {overnight_charges:.2f} pts")

    # Drawdown warning
    dd_diff = overnight_summary['max_drawdown_pts'] - eod_summary['max_drawdown_pts']
    if dd_diff < -20:
        add_line(f"⚠️  Higher drawdown with overnight: {dd_diff:.2f} pts worse - ensure adequate capital")

    add_line("")
    add_line("=" * 100)

    # Save to file if requested
    if output_file:
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
        print(f"\n✅ Comparison saved to: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Compare EOD Exit vs Overnight Hold strategies'
    )

    parser.add_argument(
        '--data-path',
        type=str,
        required=True,
        help='Path to historical data directory or CSV file'
    )

    parser.add_argument(
        '--market',
        type=str,
        required=True,
        help='Market to trade (e.g., GERMANY40, US500)'
    )

    parser.add_argument(
        '--tp',
        type=float,
        default=40,
        help='Take profit in points (default: 40)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to config file (default: config.yaml)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Optional output file to save comparison report'
    )

    args = parser.parse_args()

    print(f"\n🔍 Loading configuration from {args.config}...")

    # Load configuration
    try:
        base_config = load_config(args.config)
        config = get_market_config(base_config, args.market)
        config['market_name'] = args.market
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        sys.exit(1)

    print(f"✅ Configuration loaded")
    print(f"   Market: {config.get('symbol', 'Unknown')}")
    print(f"   Timezone: {config.get('tz', 'Unknown')}")
    print(f"   TP: {args.tp} pts")
    print(f"   Data: {args.data_path}")
    print()

    # Run EOD exit strategy
    print("📊 Running backtest with force_eod_exit=true (EOD exit)...")
    eod_trades, eod_summary = run_single_backtest(config, args.tp, True, args.data_path)

    if eod_trades is None:
        print("❌ No trades generated for EOD strategy")
        sys.exit(1)

    print(f"✅ EOD strategy complete: {len(eod_trades)} trades, P&L: {eod_summary['total_pts']:+.2f} pts")
    print()

    # Run overnight strategy
    print("📊 Running backtest with force_eod_exit=false (overnight allowed)...")
    overnight_trades, overnight_summary = run_single_backtest(config, args.tp, False, args.data_path)

    if overnight_trades is None:
        print("❌ No trades generated for overnight strategy")
        sys.exit(1)

    print(f"✅ Overnight strategy complete: {len(overnight_trades)} trades, P&L: {overnight_summary['total_pts']:+.2f} pts")
    print()

    # Display comparison
    print_comparison(eod_summary, overnight_summary, eod_trades, overnight_trades, args.output)


if __name__ == '__main__':
    main()
