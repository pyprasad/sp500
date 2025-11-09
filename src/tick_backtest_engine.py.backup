"""Tick-level backtest engine - processes tick data for realistic simulation."""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pytz
from datetime import datetime, timedelta
import logging

from .indicators import compute_rsi
from .session_clock import SessionClock
from .trailing_stop_manager import TrailingStopManager


class TickBacktestEngine:
    """
    Tick-level backtesting engine for RSI-2 strategy.

    More realistic than bar-only backtest by:
    - Processing every tick for SL/TP checks
    - Tracking trailing stop on each tick
    - Using actual bid/ask spreads from data
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize tick backtest engine.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("rsi2_strategy.tick_backtest")
        self.session_clock = SessionClock(config)

        # Strategy parameters
        self.rsi_period = config.get('rsi_period', 2)
        self.oversold = config.get('oversold', 3.0)
        self.stop_loss_pts = config.get('stop_loss_pts', 2.0)
        self.size_gbp_per_point = config.get('size_gbp_per_point', 1.0)

        # Trailing stop configuration
        self.use_trailing_stop = config.get('use_trailing_stop', False)
        self.trailing_manager = TrailingStopManager(config) if self.use_trailing_stop else None

        # EOD exit policy
        self.force_eod_exit = config.get('force_eod_exit', True)
        self.max_hold_days = config.get('max_hold_days', 0)

        # Overnight funding configuration
        self.overnight_funding_rate = config.get('overnight_funding_rate_pct', 0.035)

    def load_tick_data(self, tick_data_path: str) -> pd.DataFrame:
        """
        Load tick data from CSV file.

        Args:
            tick_data_path: Path to tick CSV file

        Returns:
            DataFrame with columns: timestamp, bid, ask
        """
        self.logger.info(f"Loading tick data from {tick_data_path}...")

        df = pd.read_csv(tick_data_path)

        # Normalize column names
        df.columns = df.columns.str.lower()

        # Parse timestamp (format varies: with/without microseconds)
        df['timestamp'] = pd.to_datetime(df['ts'], format='ISO8601', utc=True)

        # Keep only necessary columns
        df = df[['timestamp', 'bid', 'ask']].copy()

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        self.logger.info(f"Loaded {len(df):,} ticks from {df['timestamp'].min()} to {df['timestamp'].max()}")

        return df

    def build_candles_from_ticks(self, ticks_df: pd.DataFrame, timeframe_minutes: int = 30) -> pd.DataFrame:
        """
        Build OHLC candles from tick data.

        Args:
            ticks_df: DataFrame with tick data
            timeframe_minutes: Candle timeframe in minutes

        Returns:
            DataFrame with OHLC candles
        """
        self.logger.info(f"Building {timeframe_minutes}-minute candles from ticks...")

        # Use mid price for OHLC (bid+ask)/2
        ticks_df['mid'] = (ticks_df['bid'] + ticks_df['ask']) / 2

        # Set timestamp as index for resampling
        ticks_df.set_index('timestamp', inplace=True)

        # Resample to timeframe
        rule = f'{timeframe_minutes}min'
        candles = ticks_df['mid'].resample(rule).ohlc()

        # Reset index to get timestamp as column
        candles.reset_index(inplace=True)

        # Drop empty candles (no ticks)
        candles = candles.dropna()

        self.logger.info(f"Built {len(candles):,} candles")

        return candles

    def filter_session_bars(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter candles to only include session hours.

        Args:
            df: DataFrame with candles

        Returns:
            Filtered DataFrame
        """
        mask = df['timestamp'].apply(lambda ts: self.session_clock.is_session_open(ts))
        filtered = df[mask].copy()

        # Add entry_allowed flag (skip first N minutes)
        filtered['entry_allowed'] = filtered['timestamp'].apply(
            lambda ts: self.session_clock.is_entry_allowed(ts)
        )

        self.logger.info(f"Filtered to {len(filtered)} bars within session hours")

        return filtered

    def get_ticks_for_bar(self, ticks_df: pd.DataFrame, bar_start: datetime,
                          bar_duration_minutes: int = 30) -> pd.DataFrame:
        """
        Extract ticks that fall within a specific bar's timeframe.

        Args:
            ticks_df: Full tick DataFrame (with timestamp as index)
            bar_start: Bar start timestamp
            bar_duration_minutes: Bar duration in minutes

        Returns:
            Ticks within the bar period
        """
        bar_end = bar_start + timedelta(minutes=bar_duration_minutes)

        # Filter ticks within this bar
        mask = (ticks_df.index >= bar_start) & (ticks_df.index < bar_end)
        bar_ticks = ticks_df[mask].copy()

        return bar_ticks

    def _calculate_overnight_charge(self, entry_price: float, days_held: int) -> float:
        """Calculate overnight funding charge."""
        if days_held == 0:
            return 0.0
        daily_rate = self.overnight_funding_rate / 365.0
        charge_pts = entry_price * daily_rate * days_held
        return charge_pts

    def run_tick_backtest(self, ticks_df: pd.DataFrame, candles_df: pd.DataFrame, tp_pts: float) -> List[Dict[str, Any]]:
        """
        Run backtest using tick data for exit logic.

        Strategy:
        1. Use candles for RSI calculation and entry signals
        2. Use ticks for realistic SL/TP/trailing stop checking

        Args:
            ticks_df: Tick-level data
            candles_df: Pre-built candles (for RSI and entry signals)
            tp_pts: Take profit in points

        Returns:
            List of trade dictionaries
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Starting TICK-LEVEL backtest (TP={tp_pts} pts)")
        self.logger.info("=" * 60)

        # Set timestamp as index for fast lookups (if not already indexed)
        if 'timestamp' in ticks_df.columns:
            ticks_df = ticks_df.set_index('timestamp')

        # Compute RSI on candles
        candles_df['rsi'] = compute_rsi(candles_df['close'], self.rsi_period)

        trades = []
        position = None
        seen_oversold = False
        entry_signal = False
        current_date = None

        # Process each candle for entry signals
        for idx, row in candles_df.iterrows():
            bar_timestamp = row['timestamp']
            bar_date = self.session_clock.get_trading_date(bar_timestamp)

            # Reset state at start of new trading day
            if current_date is None or bar_date != current_date:
                current_date = bar_date
                if position is None:
                    seen_oversold = False
                    entry_signal = False

            # Skip if RSI not available
            if pd.isna(row['rsi']):
                continue

            # === ENTRY LOGIC (on candle close) ===
            if row['rsi'] <= self.oversold:
                seen_oversold = True

            if (position is None and
                not entry_signal and
                seen_oversold and
                row['rsi'] > self.oversold and
                row['entry_allowed']):

                entry_signal = True
                seen_oversold = False

            # Execute entry on NEXT bar
            elif entry_signal and position is None:
                # Get ticks for this bar (entry happens at first tick)
                bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                if len(bar_ticks) == 0:
                    # No ticks in this bar, use bar open price
                    entry_price = row['open']
                else:
                    # Enter at first tick's ask price
                    first_tick = bar_ticks.iloc[0]
                    entry_price = first_tick['ask']

                # Initialize position
                position = {
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                    'tp_level': entry_price + tp_pts,
                    'sl_level': entry_price - self.stop_loss_pts,
                    'bars_held': 0,
                    'days_held': 0,
                    'overnight_charges_pts': 0.0,
                }

                # Initialize trailing stop manager
                if self.trailing_manager:
                    self.trailing_manager.on_position_opened(
                        entry_price=entry_price,
                        tp_level=position['tp_level'],
                        sl_level=position['sl_level'],
                        deal_id='backtest'
                    )

                self.logger.debug(f"ENTRY at {bar_timestamp}: {entry_price:.2f} (TP: {position['tp_level']:.2f}, SL: {position['sl_level']:.2f})")

                entry_signal = False

            # === EXIT LOGIC (tick-by-tick within bar) ===
            if position is not None:
                position['bars_held'] += 1

                # Track overnight charges
                current_date_check = self.session_clock.localize_timestamp(bar_timestamp).date()
                if current_date_check != position['entry_date']:
                    days_diff = (current_date_check - position['entry_date']).days
                    if days_diff > position['days_held']:
                        nights_to_charge = days_diff - position['days_held']
                        charge = self._calculate_overnight_charge(position['entry_price'], nights_to_charge)
                        position['overnight_charges_pts'] += charge
                        position['days_held'] = days_diff

                # Get ticks for this bar
                bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                exit_price = None
                exit_reason = None
                exit_time = bar_timestamp

                # Check max hold days
                if self.max_hold_days > 0 and position['days_held'] >= self.max_hold_days:
                    exit_price = row['close']
                    exit_reason = 'MAX_HOLD_DAYS'

                # Process ticks within this bar
                if exit_price is None and len(bar_ticks) > 0:
                    for tick_time, tick in bar_ticks.iterrows():
                        bid = tick['bid']

                        # Update trailing stop (if enabled)
                        if self.trailing_manager:
                            should_update, new_sl, _ = self.trailing_manager.on_tick(bid)
                            if should_update and new_sl:
                                position['sl_level'] = new_sl

                        # Check SL hit (conservative: check SL first)
                        if bid <= position['sl_level']:
                            exit_price = position['sl_level']
                            exit_reason = 'TRAILING_SL' if (self.trailing_manager and self.trailing_manager.trailing_active) else 'SL'
                            exit_time = tick_time
                            break

                        # Check TP hit
                        if bid >= position['tp_level']:
                            exit_price = position['tp_level']
                            exit_reason = 'TP'
                            exit_time = tick_time
                            break

                # Check EOD exit
                if exit_price is None and self.force_eod_exit:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        # Exit at last tick's bid or bar close
                        if len(bar_ticks) > 0:
                            exit_price = bar_ticks.iloc[-1]['bid']
                        else:
                            exit_price = row['close']
                        exit_reason = 'EOD'

                # Close position if exit triggered
                if exit_price is not None:
                    pnl_pts_gross = exit_price - position['entry_price']
                    overnight_charges = position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': tp_pts,
                        'sl_pts': self.stop_loss_pts,
                        'datetime_close': exit_time,
                        'ny_time_close': self.session_clock.localize_timestamp(exit_time).strftime('%Y-%m-%d %H:%M:%S'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'pnl_pts': pnl_pts_net,
                        'pnl_pts_gross': pnl_pts_gross,
                        'overnight_charges': overnight_charges,
                        'days_held': position['days_held'],
                        'pnl_gbp': pnl_gbp,
                        'bars_held': position['bars_held']
                    }

                    trades.append(trade)

                    self.logger.debug(f"EXIT at {exit_time}: {exit_price:.2f} ({exit_reason}) | P&L: {pnl_pts_net:+.2f} pts")

                    # Reset position and trailing manager
                    position = None
                    if self.trailing_manager:
                        self.trailing_manager.on_position_closed()

        self.logger.info("=" * 60)
        self.logger.info(f"Tick backtest complete: {len(trades)} trades")
        self.logger.info("=" * 60)

        return trades
