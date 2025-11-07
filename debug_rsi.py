"""Debug RSI calculation discrepancies between system and IG platform."""

import pandas as pd
from pathlib import Path
from src.indicators import compute_rsi

def analyze_historical_candles():
    """Analyze the most recent historical candles CSV file."""

    # Find the most recent historical file
    historical_dir = Path('data/historical')
    if not historical_dir.exists():
        print("No historical data found. Run live trading first to fetch historical candles.")
        return

    csv_files = list(historical_dir.glob('historical_*.csv'))
    if not csv_files:
        print("No historical CSV files found.")
        return

    # Get most recent file
    latest_file = max(csv_files, key=lambda p: p.stat().st_mtime)
    print(f"Analyzing: {latest_file.name}\n")

    # Load data
    df = pd.read_csv(latest_file)
    print(f"Loaded {len(df)} candles")
    print(f"Date range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}\n")

    # Show last 10 candles
    print("="*80)
    print("LAST 10 CANDLES:")
    print("="*80)
    print(df[['timestamp', 'open', 'high', 'low', 'close']].tail(10).to_string(index=False))
    print()

    # Compute RSI
    rsi = compute_rsi(df['close'], period=2)
    df['rsi'] = rsi

    # Show last 10 RSI values
    print("="*80)
    print("LAST 10 RSI VALUES:")
    print("="*80)
    last_10 = df[['timestamp', 'close', 'rsi']].tail(10).copy()

    # Calculate price changes for reference
    last_10['change'] = last_10['close'].diff()

    print(last_10.to_string(index=False))
    print()

    # Show final RSI
    final_rsi = df['rsi'].iloc[-1]
    print("="*80)
    print(f"FINAL RSI(2): {final_rsi:.2f}")
    print("="*80)
    print()

    # Show calculation details for last few bars
    print("="*80)
    print("DETAILED RSI CALCULATION (Last 5 bars):")
    print("="*80)

    closes = df['close'].tail(7).values  # Need 7 for RSI(2) + deltas
    print(f"\nClose prices: {closes}")

    deltas = pd.Series(closes).diff()
    gains = deltas.where(deltas > 0, 0.0)
    losses = -deltas.where(deltas < 0, 0.0)

    print(f"Deltas:  {deltas.values}")
    print(f"Gains:   {gains.values}")
    print(f"Losses:  {losses.values}")
    print()

    # Show avg gain/loss for last value
    print("Wilder's Smoothing Calculation:")
    print(f"- First avg_gain (bar 2): {gains.iloc[1:3].mean():.4f}")
    print(f"- First avg_loss (bar 2): {losses.iloc[1:3].mean():.4f}")
    print()

    print("Tips for matching IG:")
    print("1. Verify IG RSI period is set to 2 (not 14)")
    print("2. Check if IG is using mid prices, bid, ask, or last traded")
    print("3. Ensure you're comparing the same time/candle")
    print("4. More historical data improves Wilder's smoothing accuracy")
    print()

if __name__ == '__main__':
    analyze_historical_candles()
