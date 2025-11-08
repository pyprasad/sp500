"""Compare Fixed TP vs different Trailing Stop configurations."""

import pandas as pd
from pathlib import Path

from src.bt_engine import BacktestEngine
from src.indicators import compute_rsi
from src.utils import load_config, get_market_config


def test_trailing_config(df, base_config, tp_pts, use_trailing, activation, distance):
    """Test a specific trailing stop configuration."""
    config = base_config.copy()
    config['use_trailing_stop'] = use_trailing
    config['trailing_stop_activation_pts'] = activation
    config['trailing_stop_distance_pts'] = distance

    engine = BacktestEngine(config)
    results = engine.run_backtest(df.copy(), tp_pts)

    if not results:
        return None

    trades_df = pd.DataFrame(results)
    total_pnl = trades_df['pnl_pts'].sum()
    num_trades = len(trades_df)
    expectancy = total_pnl / num_trades if num_trades > 0 else 0

    tp_exits = len(trades_df[trades_df['exit_reason'] == 'TP'])
    trailing_exits = len(trades_df[trades_df['exit_reason'] == 'TRAILING_SL'])
    sl_exits = len(trades_df[trades_df['exit_reason'] == 'SL'])

    return {
        'use_trailing': use_trailing,
        'activation': activation if use_trailing else 0,
        'distance': distance if use_trailing else 0,
        'total_pnl': total_pnl,
        'num_trades': num_trades,
        'expectancy': expectancy,
        'tp_exits': tp_exits,
        'trailing_exits': trailing_exits,
        'sl_exits': sl_exits
    }


def main():
    data_path = 'data/backtest/germany40'
    market = 'GERMANY40'
    tp_pts = 40

    print("="*80)
    print("TRAILING STOP OPTIMIZATION")
    print("="*80)
    print(f"Market: {market}")
    print(f"Fixed TP: {tp_pts} pts")
    print(f"Testing different trailing stop configurations...")
    print("="*80)
    print()

    # Load config and data
    config = load_config('config.yaml')
    config = get_market_config(config, market)

    engine = BacktestEngine(config)
    df = engine.load_data(data_path)
    df = engine.filter_session_bars(df)

    # Compute RSI and signals
    rsi = compute_rsi(df['close'], config.get('rsi_period', 2))
    df['rsi'] = rsi

    oversold = config.get('oversold', 5.0)
    df['rsi_prev'] = df['rsi'].shift(1)
    df['signal'] = (
        (df['rsi_prev'] <= oversold) &
        (df['rsi'] > oversold) &
        (df['entry_allowed'])
    )

    # Test configurations
    configs = [
        # Fixed TP (baseline)
        (False, 0, 0, "Fixed TP (baseline)"),

        # Trailing with different activations and distances
        (True, 10, 10, "Trailing: Activate@10, Distance=10"),
        (True, 20, 10, "Trailing: Activate@20, Distance=10"),
        (True, 20, 15, "Trailing: Activate@20, Distance=15"),
        (True, 20, 20, "Trailing: Activate@20, Distance=20"),
        (True, 30, 15, "Trailing: Activate@30, Distance=15"),
        (True, 30, 20, "Trailing: Activate@30, Distance=20"),
        (True, 40, 20, "Trailing: Activate@40, Distance=20"),
        (True, 40, 30, "Trailing: Activate@40, Distance=30"),
    ]

    results = []
    for use_trailing, activation, distance, description in configs:
        result = test_trailing_config(df, config, tp_pts, use_trailing, activation, distance)
        if result:
            result['description'] = description
            results.append(result)
            print(f"{description:45s}: P&L={result['total_pnl']:+8.2f} pts, "
                  f"Expect={result['expectancy']:+6.2f}, "
                  f"TP={result['tp_exits']:3d}, Trail={result['trailing_exits']:3d}")

    print()
    print("="*80)
    print("COMPARISON SUMMARY")
    print("="*80)
    print()

    # Sort by P&L
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('total_pnl', ascending=False)

    print("Top 5 by Total P&L:")
    print()
    for idx, row in results_df.head(5).iterrows():
        print(f"  {idx+1}. {row['description']}")
        print(f"     Total P&L: {row['total_pnl']:+.2f} pts")
        print(f"     Expectancy: {row['expectancy']:+.2f} pts/trade")
        print(f"     TP exits: {row['tp_exits']}, Trailing exits: {row['trailing_exits']}")
        print()

    # Save results
    output_file = 'reports/trailing_stop_comparison.csv'
    Path('reports').mkdir(exist_ok=True)
    results_df.to_csv(output_file, index=False)
    print(f"Full results saved to: {output_file}")
    print()


if __name__ == '__main__':
    main()
