"""Technical indicators calculation."""

import numpy as np
import pandas as pd
from typing import Union


def compute_rsi(prices: Union[pd.Series, np.ndarray], period: int = 2) -> pd.Series:
    """
    Compute RSI (Relative Strength Index) using Wilder's smoothing method.

    This implementation follows the original RSI calculation by J. Welles Wilder:
    - First average: Simple mean of first N gains/losses
    - Subsequent averages: Exponential smoothing with alpha = 1/N
      Formula: AvgU_t = (1/N) * U_t + ((N-1)/N) * AvgU_t-1

    Args:
        prices: Series or array of prices
        period: RSI period (default 2)

    Returns:
        RSI values as pandas Series
    """
    if isinstance(prices, np.ndarray):
        prices = pd.Series(prices)

    # Calculate price changes
    delta = prices.diff()

    # Separate gains and losses
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)

    # Wilder's smoothing method (exponential smoothing with alpha = 1/period)
    # First, calculate simple average for the first 'period' values
    avg_gains = pd.Series(index=prices.index, dtype=float)
    avg_losses = pd.Series(index=prices.index, dtype=float)

    # Initialize with NaN
    avg_gains[:] = np.nan
    avg_losses[:] = np.nan

    # Calculate first average using simple mean
    if len(gains) >= period + 1:  # +1 because first delta is NaN
        first_avg_gain = gains.iloc[1:period+1].mean()
        first_avg_loss = losses.iloc[1:period+1].mean()

        avg_gains.iloc[period] = first_avg_gain
        avg_losses.iloc[period] = first_avg_loss

        # Apply Wilder's smoothing for subsequent values
        # Formula: new_avg = (1/N) * current + ((N-1)/N) * prev_avg
        alpha = 1.0 / period
        for i in range(period + 1, len(prices)):
            avg_gains.iloc[i] = alpha * gains.iloc[i] + (1 - alpha) * avg_gains.iloc[i-1]
            avg_losses.iloc[i] = alpha * losses.iloc[i] + (1 - alpha) * avg_losses.iloc[i-1]

    # Calculate RS and RSI
    rs = avg_gains / avg_losses
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def detect_oversold_rebound(rsi: pd.Series, threshold: float = 3.0) -> pd.Series:
    """
    Detect RSI rebound signals (crosses up through threshold after being at/under threshold).

    Args:
        rsi: RSI series
        threshold: Oversold threshold

    Returns:
        Boolean series indicating rebound signals
    """
    # Track when RSI is at or below threshold
    oversold = rsi <= threshold

    # Detect crossover: RSI crosses above threshold
    crossover = (rsi > threshold) & (rsi.shift(1) <= threshold)

    # Signal is valid only if we've seen oversold condition
    # Use expanding max to track if we've ever seen oversold before each point
    seen_oversold = oversold.expanding().max().astype(bool)

    # Reset seen_oversold after each crossover
    signals = pd.Series(False, index=rsi.index)
    seen = False

    for i in range(len(rsi)):
        if pd.notna(rsi.iloc[i]):
            if rsi.iloc[i] <= threshold:
                seen = True
            elif seen and rsi.iloc[i] > threshold:
                if i > 0 and rsi.iloc[i-1] <= threshold:
                    signals.iloc[i] = True
                    seen = False

    return signals
