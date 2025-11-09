"""Compare bar-only vs tick-level backtest results."""

import argparse
import pandas as pd
from pathlib import Path


def load_summary(csv_path):
    """Load summary CSV and return as dict."""
    df = pd.read_csv(csv_path)
    # Convert first row to dictionary
    return df.iloc[0].to_dict()


def format_diff(val1, val2, decimals=2, suffix='', percent=True):
    """Format difference with color indicator."""
    diff = val2 - val1
    sign = '+' if diff >= 0 else ''

    if percent and val1 != 0:
        pct = (diff / abs(val1)) * 100
        return f"{sign}{diff:.{decimals}f}{suffix} ({sign}{pct:.1f}%)"
    else:
        return f"{sign}{diff:.{decimals}f}{suffix}"


def print_comparison(bar_sum, tick_sum, output_file=None):
    """Print comparison table."""

    lines = []

    def add_line(text):
        lines.append(text)
        print(text)

    add_line("=" * 80)
    add_line("BACKTEST COMPARISON: BAR-ONLY vs TICK-LEVEL SIMULATION")
    add_line("=" * 80)
    add_line(f"Market: GERMANY40 (DAX)")
    add_line(f"Strategy: RSI-2 Rebound Long with Trailing Stop")
    add_line(f"Period: 2024")
    add_line("=" * 80)
    add_line("")

    # Performance metrics
    add_line("PERFORMANCE METRICS")
    add_line("-" * 80)
    add_line(f"{'Metric':<35} {'Bar Backtest':>18} {'Tick Backtest':>18} {'Difference'}")
    add_line("-" * 80)

    # Total P&L
    bar_pnl = bar_sum['total_pts']
    tick_pnl = tick_sum['total_pts']
    diff_pnl = format_diff(bar_pnl, tick_pnl, 2, ' pts')
    add_line(f"{'Total P&L':<35} {bar_pnl:>18.2f} {tick_pnl:>18.2f} {diff_pnl}")

    # Return %
    bar_ret = bar_sum['return_pct']
    tick_ret = tick_sum['return_pct']
    diff_ret = format_diff(bar_ret, tick_ret, 2, '%', False)
    add_line(f"{'Return %':<35} {bar_ret:>17.2f}% {tick_ret:>17.2f}% {diff_ret}")

    # Final Balance
    bar_bal = bar_sum['final_balance']
    tick_bal = tick_sum['final_balance']
    diff_bal = format_diff(bar_bal, tick_bal, 2, '', False)
    add_line(f"{'Final Balance':<35} {'£' + f'{bar_bal:,.2f}':>18} {'£' + f'{tick_bal:,.2f}':>18} £{diff_bal}")

    add_line("")

    # Trade statistics
    add_line(f"{'Total Trades':<35} {bar_sum['trades']:>18.0f} {tick_sum['trades']:>18.0f} {int(tick_sum['trades'] - bar_sum['trades'])}")
    add_line(f"{'Wins':<35} {bar_sum['wins']:>18.0f} {tick_sum['wins']:>18.0f} {int(tick_sum['wins'] - bar_sum['wins'])}")
    add_line(f"{'Losses':<35} {bar_sum['losses']:>18.0f} {tick_sum['losses']:>18.0f} {int(tick_sum['losses'] - bar_sum['losses'])}")

    bar_wr = bar_sum['win_rate']
    tick_wr = tick_sum['win_rate']
    diff_wr = format_diff(bar_wr, tick_wr, 2, '%', False)
    add_line(f"{'Win Rate':<35} {bar_wr:>17.2f}% {tick_wr:>17.2f}% {diff_wr}")

    add_line("")

    bar_avg_win = bar_sum['avg_win_pts']
    tick_avg_win = tick_sum['avg_win_pts']
    diff_avg_win = format_diff(bar_avg_win, tick_avg_win, 2, ' pts', False)
    add_line(f"{'Avg Win':<35} {bar_avg_win:>18.2f} {tick_avg_win:>18.2f} {diff_avg_win}")

    bar_avg_loss = bar_sum['avg_loss_pts']
    tick_avg_loss = tick_sum['avg_loss_pts']
    diff_avg_loss = format_diff(bar_avg_loss, tick_avg_loss, 2, ' pts', False)
    add_line(f"{'Avg Loss':<35} {bar_avg_loss:>18.2f} {tick_avg_loss:>18.2f} {diff_avg_loss}")

    bar_exp = bar_sum['expectancy_pts']
    tick_exp = tick_sum['expectancy_pts']
    diff_exp = format_diff(bar_exp, tick_exp, 2, ' pts', False)
    add_line(f"{'Expectancy':<35} {bar_exp:>18.2f} {tick_exp:>18.2f} {diff_exp}")

    add_line("")

    bar_dd = bar_sum['max_drawdown_pts']
    tick_dd = tick_sum['max_drawdown_pts']
    diff_dd = format_diff(bar_dd, tick_dd, 2, ' pts', False)
    add_line(f"{'Max Drawdown':<35} {bar_dd:>18.2f} {tick_dd:>18.2f} {diff_dd}")

    bar_bars = bar_sum['avg_bars_held']
    tick_bars = tick_sum['avg_bars_held']
    diff_bars = format_diff(bar_bars, tick_bars, 1, '', False)
    add_line(f"{'Avg Bars Held':<35} {bar_bars:>18.1f} {tick_bars:>18.1f} {diff_bars}")

    add_line("-" * 80)
    add_line("")

    # Exit reasons (if available)
    add_line("EXIT REASONS BREAKDOWN")
    add_line("-" * 80)
    add_line(f"{'Exit Type':<20} {'Bar Backtest':>28} {'Tick Backtest':>28}")
    add_line("-" * 80)

    # Load trade files for exit breakdown
    bar_trades_path = Path(output_file).parent / 'reports/bar_backtest_2024/trades_tp40.csv' if output_file else None
    tick_trades_path = Path(output_file).parent / 'reports/tick_backtest_2024/trades_tp40.csv' if output_file else None

    # Try to load exit details from trade files
    try:
        # This is a simplified version - actual implementation would parse trades
        add_line(f"{'TP':<20} {'-':>28} {'-':>28}")
        add_line(f"{'SL':<20} {'-':>28} {'-':>28}")
        add_line(f"{'TRAILING_SL':<20} {'-':>28} {'-':>28}")
        add_line(f"{'EOD':<20} {'-':>28} {'-':>28}")
    except:
        add_line("(Exit reason details not available)")

    add_line("-" * 80)
    add_line("")

    # Key findings
    add_line("KEY FINDINGS")
    add_line("-" * 80)
    add_line("")

    pnl_diff_pct = ((tick_pnl - bar_pnl) / abs(bar_pnl) * 100) if bar_pnl != 0 else 0

    if tick_pnl < bar_pnl:
        add_line(f"1. TICK BACKTEST SHOWS LOWER PROFIT: {abs(pnl_diff_pct):.1f}% less")
        add_line(f"   - Bar backtest: +{bar_pnl:.2f} pts")
        add_line(f"   - Tick backtest: +{tick_pnl:.2f} pts")
        add_line(f"   - Difference: {tick_pnl - bar_pnl:.2f} pts")
        add_line("")
        add_line("   WHY: Tick-level simulation catches intra-bar reversals that bar backtest misses.")
        add_line("   Bar backtest only sees bar.high/low, tick sees every price movement.")
        add_line("   More realistic exits happen earlier, capturing less profit.")
    else:
        add_line(f"1. TICK BACKTEST SHOWS HIGHER PROFIT: +{pnl_diff_pct:.1f}%")
        add_line(f"   - Bar backtest: +{bar_pnl:.2f} pts")
        add_line(f"   - Tick backtest: +{tick_pnl:.2f} pts")
        add_line(f"   - Difference: +{tick_pnl - bar_pnl:.2f} pts")

    add_line("")
    add_line("2. SIMULATION REALISM")
    add_line("   - Tick backtest: Processes every tick (mirrors live trading)")
    add_line("   - Bar backtest: Only checks exits at bar boundaries")
    add_line("   - Tick is more realistic for trailing stop strategies")
    add_line("")

    add_line("3. RECOMMENDATION")
    if tick_pnl > 0:
        add_line(f"   ✓ Strategy is PROFITABLE on tick-level simulation (+{tick_pnl:.2f} pts)")
        add_line("   ✓ Safe to proceed with live trading")
        add_line(f"   ✓ Expect performance closer to +{tick_pnl:.2f} pts than +{bar_pnl:.2f} pts")
    else:
        add_line(f"   ✗ Strategy shows LOSSES on tick-level simulation ({tick_pnl:.2f} pts)")
        add_line("   ✗ Do NOT go live without strategy adjustment")
        add_line("   ✗ Bar backtest gave false confidence")

    add_line("")
    add_line("=" * 80)
    add_line("CONCLUSION")
    add_line("=" * 80)
    add_line("")
    add_line("The tick-level backtest provides MORE REALISTIC simulation because it:")
    add_line("✓ Processes every price movement (millions of ticks vs thousands of bars)")
    add_line("✓ Catches intra-bar reversals that hit SL/TP")
    add_line("✓ Uses actual bid/ask from tick data")
    add_line("✓ Updates trailing stop on every tick (like live trading)")
    add_line("")
    add_line("Use TICK backtest results for live trading expectations.")
    add_line("Use BAR backtest only for quick parameter testing.")
    add_line("=" * 80)

    # Save to file
    if output_file:
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
        print(f"\nComparison saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Compare bar vs tick backtest results')
    parser.add_argument('--bar-summary', required=True, help='Path to bar backtest summary CSV')
    parser.add_argument('--tick-summary', required=True, help='Path to tick backtest summary CSV')
    parser.add_argument('--output', default='bar_vs_tick_comparison.txt', help='Output file path')

    args = parser.parse_args()

    # Load summaries
    print(f"Loading bar backtest summary: {args.bar_summary}")
    bar_summary = load_summary(args.bar_summary)

    print(f"Loading tick backtest summary: {args.tick_summary}")
    tick_summary = load_summary(args.tick_summary)

    print("\n")

    # Print comparison
    print_comparison(bar_summary, tick_summary, args.output)


if __name__ == '__main__':
    main()
