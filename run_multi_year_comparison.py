#!/usr/bin/env python3
"""
Run backtests across multiple years and strategies, then produce a comparison table.

Usage:
    python3 run_multi_year_comparison.py

This will:
1. Run LONG, SHORT, and BOTH modes for each year (2020-2024)
2. Generate a comparison table showing P&L for each year/mode
3. Save results to reports/multi_year_comparison/
"""

import subprocess
import pandas as pd
from pathlib import Path
import json
import sys


def run_backtest(year: int, mode: str, tick_data_path: str, output_dir: str) -> dict:
    """
    Run a single backtest and return results.

    Args:
        year: Year being tested
        mode: "long", "short", or "both"
        tick_data_path: Path to tick data CSV
        output_dir: Output directory for reports

    Returns:
        dict with results (total_pnl_pts, total_pnl_gbp, trades, win_rate, etc.)
    """
    print(f"\n{'='*60}")
    print(f"Running {mode.upper()} backtest for {year}...")
    print(f"{'='*60}")

    # Update config.yaml temporarily
    import yaml
    config_path = "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    original_mode = config.get('strategy_mode')
    config['strategy_mode'] = mode

    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    try:
        # Run tick backtest
        cmd = [
            'python3', '-m', 'src.tick_backtest',
            '--tick-data', tick_data_path,
            '--tp', '40',
            '--market', 'GERMANY40',
            '--out', output_dir
        ]

        # Increase timeout for large files (2020 has 4.4GB!)
        # Estimated time: ~30-60 min for large years
        # Use check=False to handle errors gracefully
        result = subprocess.run(cmd, capture_output=False, text=True, timeout=3600, check=False)

        if result.returncode != 0:
            print(f"ERROR: Backtest failed for {year} {mode} (exit code: {result.returncode})")
            return None

        # Read summary file
        summary_file = Path(output_dir) / "summary_tp40.csv"
        if not summary_file.exists():
            print(f"ERROR: Summary file not found: {summary_file}")
            return None

        summary_df = pd.read_csv(summary_file)
        summary = summary_df.iloc[0].to_dict()

        print(f"✓ {mode.upper()}: {summary['trades']} trades, {summary['total_pts']:+.2f} pts, {summary['return_pct']:+.2f}%")

        return summary

    finally:
        # Restore original config
        config['strategy_mode'] = original_mode
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def main():
    """Run multi-year comparison."""

    # Configuration
    years = [2012, 2020, 2021, 2022, 2023, 2024]
    modes = ['long', 'short', 'both']
    base_data_path = Path("data/backtest")
    base_output_path = Path("reports/multi_year_comparison")

    # Create output directory
    base_output_path.mkdir(parents=True, exist_ok=True)

    # Collect results
    results = []

    for year in years:
        # Find tick data file
        year_dir = base_data_path / f"germany40_{year}"
        tick_file = year_dir / f"dax_{year}_full_scaled.csv"

        if not tick_file.exists():
            print(f"\nWARNING: Tick data not found for {year}: {tick_file}")
            print(f"Skipping {year}...")
            continue

        year_results = {'year': year}

        for mode in modes:
            output_dir = base_output_path / f"{year}_{mode}"

            summary = run_backtest(year, mode, str(tick_file), str(output_dir))

            if summary:
                year_results[f'{mode}_trades'] = int(summary.get('trades', 0))
                year_results[f'{mode}_pnl_pts'] = round(float(summary.get('total_pts', 0)), 2)
                year_results[f'{mode}_pnl_gbp'] = round(float(summary.get('total_gbp', 0)), 2)
                year_results[f'{mode}_win_rate'] = round(float(summary.get('win_rate', 0)), 2)
                year_results[f'{mode}_return_pct'] = round(float(summary.get('return_pct', 0)), 2)
            else:
                year_results[f'{mode}_trades'] = 0
                year_results[f'{mode}_pnl_pts'] = 0.0
                year_results[f'{mode}_pnl_gbp'] = 0.0
                year_results[f'{mode}_win_rate'] = 0.0
                year_results[f'{mode}_return_pct'] = 0.0

        results.append(year_results)

    # Create comparison DataFrame
    df = pd.DataFrame(results)

    # Save detailed results
    detailed_csv = base_output_path / "detailed_comparison.csv"
    df.to_csv(detailed_csv, index=False)
    print(f"\n✓ Detailed results saved to: {detailed_csv}")

    # Create simple P&L table
    simple_data = []
    for _, row in df.iterrows():
        simple_data.append({
            'Year': int(row['year']),
            'LONG (pts)': f"{row['long_pnl_pts']:+.2f}",
            'SHORT (pts)': f"{row['short_pnl_pts']:+.2f}",
            'BOTH (pts)': f"{row['both_pnl_pts']:+.2f}",
            'LONG (£)': f"£{row['long_pnl_gbp']:+,.2f}",
            'SHORT (£)': f"£{row['short_pnl_gbp']:+,.2f}",
            'BOTH (£)': f"£{row['both_pnl_gbp']:+,.2f}"
        })

    simple_df = pd.DataFrame(simple_data)
    simple_csv = base_output_path / "simple_pnl_comparison.csv"
    simple_df.to_csv(simple_csv, index=False)

    # Print comparison table
    print("\n" + "="*80)
    print("MULTI-YEAR P&L COMPARISON")
    print("="*80)
    print(simple_df.to_string(index=False))
    print("="*80)

    # Calculate totals
    total_long_pts = df['long_pnl_pts'].sum()
    total_short_pts = df['short_pnl_pts'].sum()
    total_both_pts = df['both_pnl_pts'].sum()
    total_long_gbp = df['long_pnl_gbp'].sum()
    total_short_gbp = df['short_pnl_gbp'].sum()
    total_both_gbp = df['both_pnl_gbp'].sum()

    print("\nTOTALS (all years):")
    print(f"  LONG:  {total_long_pts:+.2f} pts  |  £{total_long_gbp:+,.2f}")
    print(f"  SHORT: {total_short_pts:+.2f} pts  |  £{total_short_gbp:+,.2f}")
    print(f"  BOTH:  {total_both_pts:+.2f} pts  |  £{total_both_gbp:+,.2f}")
    print("="*80)

    print(f"\n✓ Simple comparison saved to: {simple_csv}")
    print(f"✓ All reports saved to: {base_output_path}/")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
