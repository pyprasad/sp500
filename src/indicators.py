"""Technical indicators calculation."""

import numpy as np
import pandas as pd
from typing import Union


def compute_rsi(prices: Union[pd.Series, np.ndarray], period: int = 2) -> pd.Series:
    """
    Compute RSI (Relative Strength Index).

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

    # Calculate average gains and losses using Wilder's smoothing
    avg_gains = gains.rolling(window=period, min_periods=period).mean()
    avg_losses = losses.rolling(window=period, min_periods=period).mean()

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
