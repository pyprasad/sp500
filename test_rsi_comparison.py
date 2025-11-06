"""Test to verify RSI calculation using Wilder's smoothing method."""

import pandas as pd
from src.indicators import compute_rsi

# Test data: Simple price sequence
prices = pd.Series([
    100.0,  # Starting price
    102.0,  # +2 gain
    101.0,  # -1 loss
    103.0,  # +2 gain
    102.5,  # -0.5 loss
    104.0,  # +1.5 gain
    103.0,  # -1 loss
    105.0,  # +2 gain
    104.0,  # -1 loss
    106.0,  # +2 gain
])

print("Price sequence:")
print(prices.to_string())
print("\n" + "="*60)

# Compute RSI with period=2
rsi = compute_rsi(prices, period=2)

print("\nRSI(2) calculation using Wilder's smoothing:")
print("-" * 60)

# Show detailed calculation for understanding
delta = prices.diff()
gains = delta.where(delta > 0, 0.0)
losses = -delta.where(delta < 0, 0.0)

df = pd.DataFrame({
    'Price': prices,
    'Delta': delta,
    'Gain': gains,
    'Loss': losses,
    'RSI': rsi
})

print(df.to_string())
print("\n" + "="*60)

# Show first valid RSI
first_valid_idx = rsi.first_valid_index()
if first_valid_idx is not None:
    print(f"\nFirst valid RSI at index {first_valid_idx}: {rsi[first_valid_idx]:.2f}")
    print(f"This is calculated after {first_valid_idx} price points")

# Show last RSI
last_rsi = rsi.iloc[-1]
print(f"Last RSI: {last_rsi:.2f}")

print("\n" + "="*60)
print("Explanation:")
print("-" * 60)
print("1. First RSI is at index 2 (after 2 price changes)")
print("2. Initial avg_gain = mean(first 2 gains) = (2.0 + 0.0) / 2 = 1.0")
print("3. Initial avg_loss = mean(first 2 losses) = (0.0 + 1.0) / 2 = 0.5")
print("4. RS = 1.0 / 0.5 = 2.0")
print("5. RSI = 100 - (100 / (1 + 2.0)) = 66.67")
print("\nSubsequent RSI values use exponential smoothing:")
print("   new_avg = (1/2) * current + (1/2) * prev_avg")
print("="*60)
