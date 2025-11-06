"""Strategy logic for RSI-2 rebound."""

import logging
import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from .indicators import compute_rsi
from .session_clock import SessionClock


class RSI2Strategy:
    """RSI-2 rebound strategy implementation."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.session_clock = SessionClock(config)
        self.logger = logging.getLogger("rsi2_strategy.strategy")

        # Strategy parameters
        self.rsi_period = config.get('rsi_period', 2)
        self.oversold = config.get('oversold', 3.0)

        # State
        self.candles = []
        self.rsi_values = []
        self.seen_oversold = False
        self.current_position: Optional[Dict[str, Any]] = None

    def add_candle(self, candle: Dict[str, Any]):
        """
        Add new candle to strategy.

        Args:
            candle: Candle dict with timestamp, open, high, low, close, volume
        """
        self.candles.append(candle)

        # Keep only necessary history (RSI period + some buffer)
        if len(self.candles) > self.rsi_period + 50:
            self.candles = self.candles[-(self.rsi_period + 50):]

    def compute_indicators(self):
        """Compute RSI on current candle data."""
        if len(self.candles) < self.rsi_period + 1:
            return

        # Extract close prices
        closes = pd.Series([c['close'] for c in self.candles])

        # Compute RSI
        rsi = compute_rsi(closes, self.rsi_period)

        # Store RSI values
        self.rsi_values = rsi.tolist()

    def get_current_rsi(self) -> Optional[float]:
        """Get most recent RSI value."""
        if not self.rsi_values or pd.isna(self.rsi_values[-1]):
            return None
        return self.rsi_values[-1]

    def check_entry_signal(self, current_time: datetime) -> bool:
        """
        Check if entry signal is triggered.

        Args:
            current_time: Current timestamp

        Returns:
            True if entry signal is present
        """
        # Skip if position already open
        if self.current_position is not None:
            return False

        # Skip if not enough data
        if len(self.rsi_values) < 2:
            return False

        # Get current and previous RSI
        rsi_current = self.rsi_values[-1]
        rsi_prev = self.rsi_values[-2]

        if pd.isna(rsi_current) or pd.isna(rsi_prev):
            return False

        # Check for oversold condition
        if rsi_current <= self.oversold:
            self.seen_oversold = True
            self.logger.debug(f"RSI oversold: {rsi_current:.2f}")

        # Check for rebound: RSI crosses above threshold after being oversold
        if (self.seen_oversold and
            rsi_prev <= self.oversold and
            rsi_current > self.oversold):

            # Check session timing
            if not self.session_clock.is_entry_allowed(current_time):
                self.logger.debug(f"Entry signal but outside entry window")
                return False

            self.logger.info(f"Entry signal! RSI crossed above {self.oversold} "
                           f"(prev: {rsi_prev:.2f}, current: {rsi_current:.2f})")
            self.seen_oversold = False
            return True

        return False

    def check_eod_exit(self, current_time: datetime) -> bool:
        """
        Check if EOD exit is required.

        Args:
            current_time: Current timestamp

        Returns:
            True if should exit at EOD
        """
        if self.current_position is None:
            return False

        return self.session_clock.is_eod_bar(current_time, bar_duration_minutes=30)

    def open_position(self, entry_price: float, tp_pts: float, sl_pts: float, timestamp: datetime):
        """
        Open new position.

        Args:
            entry_price: Entry price (ask)
            tp_pts: Take profit in points
            sl_pts: Stop loss in points
            timestamp: Entry timestamp
        """
        self.current_position = {
            'entry_price': entry_price,
            'entry_time': timestamp,
            'tp_pts': tp_pts,
            'sl_pts': sl_pts,
            'tp_level': entry_price + tp_pts,
            'sl_level': entry_price - sl_pts
        }

        self.logger.info(f"Position opened at {entry_price:.2f} "
                        f"(TP: {self.current_position['tp_level']:.2f}, "
                        f"SL: {self.current_position['sl_level']:.2f})")

    def close_position(self, exit_price: float, exit_reason: str, timestamp: datetime) -> Dict[str, Any]:
        """
        Close current position.

        Args:
            exit_price: Exit price (bid)
            exit_reason: Reason for exit (TP/SL/EOD)
            timestamp: Exit timestamp

        Returns:
            Trade dictionary
        """
        if self.current_position is None:
            raise ValueError("No position to close")

        pnl_pts = exit_price - self.current_position['entry_price']
        pnl_gbp = pnl_pts * self.config.get('size_gbp_per_point', 1.0)

        trade = {
            'entry_time': self.current_position['entry_time'],
            'entry_price': self.current_position['entry_price'],
            'exit_time': timestamp,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'tp_pts': self.current_position['tp_pts'],
            'sl_pts': self.current_position['sl_pts'],
            'pnl_pts': pnl_pts,
            'pnl_gbp': pnl_gbp
        }

        self.logger.info(f"Position closed at {exit_price:.2f} ({exit_reason}). "
                        f"P&L: {pnl_pts:.2f} pts / {pnl_gbp:.2f} GBP")

        self.current_position = None
        return trade

    def has_position(self) -> bool:
        """Check if position is open."""
        return self.current_position is not None

    def get_position(self) -> Optional[Dict[str, Any]]:
        """Get current position."""
        return self.current_position

    def reset_daily_state(self):
        """Reset state at start of new trading day."""
        if not self.has_position():
            self.seen_oversold = False
            self.logger.debug("Reset daily state")
