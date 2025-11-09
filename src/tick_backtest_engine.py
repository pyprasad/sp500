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

        # Global strategy parameters
        self.rsi_period = config.get('rsi_period', 2)
        self.size_gbp_per_point = config.get('size_gbp_per_point', 2.0)

        # Strategy mode: "long", "short", or "both"
        self.strategy_mode = config.get('strategy_mode', 'long')

        # LONG strategy settings (with fallback to legacy config)
        long_config = config.get('long', {})
        self.long_enabled = long_config.get('enabled', True)
        self.long_oversold = long_config.get('oversold_threshold', config.get('oversold', 5.0))
        self.long_tp = long_config.get('tp_pts', config.get('take_profits_pts', 40))
        self.long_sl = long_config.get('sl_pts', config.get('stop_loss_pts', 100))
        self.long_use_trailing = long_config.get('use_trailing_stop', config.get('use_trailing_stop', True))
        self.long_trailing_activation = long_config.get('trailing_activation_pts', config.get('trailing_stop_activation_pts', 25))
        self.long_trailing_distance = long_config.get('trailing_distance_pts', config.get('trailing_stop_distance_pts', 10))
        self.long_force_eod = long_config.get('force_eod_exit', config.get('force_eod_exit', True))
        self.long_max_hold_days = long_config.get('max_hold_days', config.get('max_hold_days', 0))

        # SHORT strategy settings
        short_config = config.get('short', {})
        self.short_enabled = short_config.get('enabled', False)
        self.short_overbought = short_config.get('overbought_threshold', 96.0)
        self.short_tp = short_config.get('tp_pts', 40)
        self.short_sl = short_config.get('sl_pts', 80)
        self.short_use_trailing = short_config.get('use_trailing_stop', True)
        self.short_trailing_activation = short_config.get('trailing_activation_pts', 25)
        self.short_trailing_distance = short_config.get('trailing_distance_pts', 10)
        self.short_force_eod = short_config.get('force_eod_exit', False)
        self.short_max_hold_days = short_config.get('max_hold_days', 0)

        # Legacy parameters for backward compatibility (deprecated)
        self.oversold = self.long_oversold
        self.stop_loss_pts = self.long_sl
        self.use_trailing_stop = self.long_use_trailing
        self.force_eod_exit = self.long_force_eod
        self.max_hold_days = self.long_max_hold_days

        # Trailing stop manager (will be created per-position in new implementation)
        self.trailing_manager = None

        # Overnight funding configuration
        self.overnight_funding_rate = config.get('overnight_funding_rate_pct', 0.035)

        # Margin validation
        from .margin_validator import MarginValidator
        self.margin_validator = MarginValidator(config)
        self.trades_blocked_margin = 0

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

        Supports LONG-only, SHORT-only, or BOTH strategies based on strategy_mode.

        Strategy:
        1. Use candles for RSI calculation and entry signals
        2. Use ticks for realistic SL/TP/trailing stop checking

        Args:
            ticks_df: Tick-level data
            candles_df: Pre-built candles (for RSI and entry signals)
            tp_pts: Take profit in points (DEPRECATED - uses config values)

        Returns:
            List of trade dictionaries
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Starting TICK-LEVEL backtest (Mode: {self.strategy_mode.upper()})")
        self.logger.info("=" * 60)

        # Route to appropriate backtest based on strategy_mode and enabled flags
        if self.strategy_mode == "long":
            if not self.long_enabled:
                self.logger.warning("LONG strategy disabled - returning empty trades")
                return []
            return self._run_tick_backtest_long(ticks_df, candles_df)
        elif self.strategy_mode == "short":
            if not self.short_enabled:
                self.logger.warning("SHORT strategy disabled - returning empty trades")
                return []
            return self._run_tick_backtest_short(ticks_df, candles_df)
        elif self.strategy_mode == "both":
            if not self.long_enabled and not self.short_enabled:
                self.logger.warning("Both strategies disabled - returning empty trades")
                return []
            return self._run_tick_backtest_both(ticks_df, candles_df)
        else:
            raise ValueError(f"Invalid strategy_mode: {self.strategy_mode}. Must be 'long', 'short', or 'both'")

    def _run_tick_backtest_long(self, ticks_df: pd.DataFrame, candles_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run LONG-only tick backtest (RSI oversold rebound).

        Args:
            ticks_df: Tick-level data
            candles_df: Pre-built candles (for RSI and entry signals)

        Returns:
            List of trade dictionaries
        """

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
            if row['rsi'] <= self.long_oversold:
                seen_oversold = True

            if (position is None and
                not entry_signal and
                seen_oversold and
                row['rsi'] > self.long_oversold and
                row['entry_allowed']):

                entry_signal = True
                seen_oversold = False

            # Execute entry on NEXT bar
            elif entry_signal and position is None:
                # Get ticks for this bar (entry happens at first tick)
                bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                if len(bar_ticks) == 0:
                    # No ticks in this bar, use bar open price (ask = open + spread/2)
                    entry_price = row['open']
                else:
                    # Enter at first tick's ask price
                    first_tick = bar_ticks.iloc[0]
                    entry_price = first_tick['ask']

                # Margin check
                can_trade, reason = self.margin_validator.can_open_position(entry_price, [])
                if not can_trade:
                    self.trades_blocked_margin += 1
                    entry_signal = False
                    continue

                # Initialize position
                position = {
                    'trade_type': 'LONG',
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                    'tp_level': entry_price + self.long_tp,
                    'sl_level': entry_price - self.long_sl,
                    'tp_pts': self.long_tp,
                    'sl_pts': self.long_sl,
                    'bars_held': 0,
                    'days_held': 0,
                    'overnight_charges_pts': 0.0,
                    'highest_bid': entry_price,  # For trailing stop tracking
                    'trailing_active': False,
                }

                self.logger.debug(f"LONG ENTRY at {bar_timestamp}: {entry_price:.2f} (TP: {position['tp_level']:.2f}, SL: {position['sl_level']:.2f})")

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
                if self.long_max_hold_days > 0 and position['days_held'] >= self.long_max_hold_days:
                    exit_price = row['close']
                    exit_reason = 'MAX_HOLD_DAYS'

                # Process ticks within this bar
                if exit_price is None and len(bar_ticks) > 0:
                    for tick_time, tick in bar_ticks.iterrows():
                        bid = tick['bid']

                        # Update highest bid for trailing stop
                        if bid > position['highest_bid']:
                            position['highest_bid'] = bid

                        # Update trailing stop (if enabled)
                        if self.long_use_trailing:
                            profit_pts = position['highest_bid'] - position['entry_price']
                            if profit_pts >= self.long_trailing_activation and not position['trailing_active']:
                                position['trailing_active'] = True

                            if position['trailing_active']:
                                new_sl = position['highest_bid'] - self.long_trailing_distance
                                if new_sl > position['sl_level']:
                                    position['sl_level'] = new_sl

                        # Check SL hit (conservative: check SL first)
                        if bid <= position['sl_level']:
                            exit_price = position['sl_level']
                            exit_reason = 'TRAILING_SL' if position['trailing_active'] else 'SL'
                            exit_time = tick_time
                            break

                        # Check TP hit
                        if bid >= position['tp_level']:
                            exit_price = position['tp_level']
                            exit_reason = 'TP'
                            exit_time = tick_time
                            break

                # Check EOD exit
                if exit_price is None and self.long_force_eod:
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
                        'trade_type': 'LONG',
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': position['tp_pts'],
                        'sl_pts': position['sl_pts'],
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

                    # Update margin validator
                    self.margin_validator.on_trade_closed(pnl_gbp)

                    trades.append(trade)

                    self.logger.debug(f"LONG EXIT at {exit_time}: {exit_price:.2f} ({exit_reason}) | P&L: {pnl_pts_net:+.2f} pts")

                    # Reset position
                    position = None

        self.logger.info("=" * 60)
        self.logger.info(f"LONG Tick backtest complete: {len(trades)} trades")
        self.logger.info("=" * 60)

        return trades

    def _run_tick_backtest_short(self, ticks_df: pd.DataFrame, candles_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run SHORT-only tick backtest (RSI overbought rebound).

        Args:
            ticks_df: Tick-level data
            candles_df: Pre-built candles (for RSI and entry signals)

        Returns:
            List of trade dictionaries
        """

        # Set timestamp as index for fast lookups (if not already indexed)
        if 'timestamp' in ticks_df.columns:
            ticks_df = ticks_df.set_index('timestamp')

        # Compute RSI on candles
        candles_df['rsi'] = compute_rsi(candles_df['close'], self.rsi_period)

        trades = []
        position = None
        seen_overbought = False
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
                    seen_overbought = False
                    entry_signal = False

            # Skip if RSI not available
            if pd.isna(row['rsi']):
                continue

            # === ENTRY LOGIC (on candle close) - INVERTED for SHORT ===
            if row['rsi'] >= self.short_overbought:
                seen_overbought = True

            if (position is None and
                not entry_signal and
                seen_overbought and
                row['rsi'] < self.short_overbought and
                row['entry_allowed']):

                entry_signal = True
                seen_overbought = False

            # Execute entry on NEXT bar
            elif entry_signal and position is None:
                # Get ticks for this bar (entry happens at first tick)
                bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                if len(bar_ticks) == 0:
                    # No ticks in this bar, use bar open price (bid = open - spread/2)
                    entry_price = row['open']
                else:
                    # Enter SHORT at first tick's bid price (sell)
                    first_tick = bar_ticks.iloc[0]
                    entry_price = first_tick['bid']

                # Margin check
                can_trade, reason = self.margin_validator.can_open_position(entry_price, [])
                if not can_trade:
                    self.trades_blocked_margin += 1
                    entry_signal = False
                    continue

                # Initialize position (INVERTED for SHORT)
                position = {
                    'trade_type': 'SHORT',
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                    'tp_level': entry_price - self.short_tp,  # TP BELOW entry
                    'sl_level': entry_price + self.short_sl,  # SL ABOVE entry
                    'tp_pts': self.short_tp,
                    'sl_pts': self.short_sl,
                    'bars_held': 0,
                    'days_held': 0,
                    'overnight_charges_pts': 0.0,
                    'lowest_ask': entry_price,  # For trailing stop tracking (track LOWEST)
                    'trailing_active': False,
                }

                self.logger.debug(f"SHORT ENTRY at {bar_timestamp}: {entry_price:.2f} (TP: {position['tp_level']:.2f}, SL: {position['sl_level']:.2f})")

                entry_signal = False

            # === EXIT LOGIC (tick-by-tick within bar) - INVERTED for SHORT ===
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
                if self.short_max_hold_days > 0 and position['days_held'] >= self.short_max_hold_days:
                    exit_price = row['close']
                    exit_reason = 'MAX_HOLD_DAYS'

                # Process ticks within this bar
                if exit_price is None and len(bar_ticks) > 0:
                    for tick_time, tick in bar_ticks.iterrows():
                        ask = tick['ask']  # SHORT exits at ASK (buy to close)

                        # Update lowest ask for trailing stop (INVERTED)
                        if ask < position['lowest_ask']:
                            position['lowest_ask'] = ask

                        # Update trailing stop (if enabled) - INVERTED
                        if self.short_use_trailing:
                            profit_pts = position['entry_price'] - position['lowest_ask']
                            if profit_pts >= self.short_trailing_activation and not position['trailing_active']:
                                position['trailing_active'] = True

                            if position['trailing_active']:
                                new_sl = position['lowest_ask'] + self.short_trailing_distance  # Trail ABOVE
                                if new_sl < position['sl_level']:  # Move DOWN only
                                    position['sl_level'] = new_sl

                        # Check SL hit (price went UP - bad for SHORT)
                        if ask >= position['sl_level']:
                            exit_price = position['sl_level']
                            exit_reason = 'TRAILING_SL' if position['trailing_active'] else 'SL'
                            exit_time = tick_time
                            break

                        # Check TP hit (price went DOWN - good for SHORT)
                        if ask <= position['tp_level']:
                            exit_price = position['tp_level']
                            exit_reason = 'TP'
                            exit_time = tick_time
                            break

                # Check EOD exit
                if exit_price is None and self.short_force_eod:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        # Exit at last tick's ask or bar close
                        if len(bar_ticks) > 0:
                            exit_price = bar_ticks.iloc[-1]['ask']
                        else:
                            exit_price = row['close']
                        exit_reason = 'EOD'

                # Close position if exit triggered
                if exit_price is not None:
                    pnl_pts_gross = position['entry_price'] - exit_price  # INVERTED for SHORT
                    overnight_charges = position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'trade_type': 'SHORT',
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': position['tp_pts'],
                        'sl_pts': position['sl_pts'],
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

                    # Update margin validator
                    self.margin_validator.on_trade_closed(pnl_gbp)

                    trades.append(trade)

                    self.logger.debug(f"SHORT EXIT at {exit_time}: {exit_price:.2f} ({exit_reason}) | P&L: {pnl_pts_net:+.2f} pts")

                    # Reset position
                    position = None

        self.logger.info("=" * 60)
        self.logger.info(f"SHORT Tick backtest complete: {len(trades)} trades")
        self.logger.info("=" * 60)

        return trades

    def _run_tick_backtest_both(self, ticks_df: pd.DataFrame, candles_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run BOTH LONG and SHORT tick backtests simultaneously.
        Tracks 2 separate positions with tick-level exit processing.

        Args:
            ticks_df: Tick-level data
            candles_df: Pre-built candles (for RSI and entry signals)

        Returns:
            List of trade dictionaries sorted by datetime
        """

        # Set timestamp as index for fast lookups (if not already indexed)
        if 'timestamp' in ticks_df.columns:
            ticks_df = ticks_df.set_index('timestamp')

        # Compute RSI on candles
        candles_df['rsi'] = compute_rsi(candles_df['close'], self.rsi_period)

        trades = []
        long_position = None
        short_position = None
        seen_oversold = False
        seen_overbought = False
        long_entry_signal = False
        short_entry_signal = False
        current_date = None

        # Process each candle for entry signals
        for idx, row in candles_df.iterrows():
            bar_timestamp = row['timestamp']
            bar_date = self.session_clock.get_trading_date(bar_timestamp)

            # Reset state at start of new trading day
            if current_date is None or bar_date != current_date:
                current_date = bar_date
                if long_position is None:
                    seen_oversold = False
                    long_entry_signal = False
                if short_position is None:
                    seen_overbought = False
                    short_entry_signal = False

            # Skip if RSI not available
            if pd.isna(row['rsi']):
                continue

            # ===== LONG ENTRY LOGIC =====
            if self.long_enabled:
                if row['rsi'] <= self.long_oversold:
                    seen_oversold = True

                if (long_position is None and
                    not long_entry_signal and
                    seen_oversold and
                    row['rsi'] > self.long_oversold and
                    row['entry_allowed']):

                    long_entry_signal = True
                    seen_oversold = False

                # Execute LONG entry on NEXT bar
                elif long_entry_signal and long_position is None:
                    bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                    if len(bar_ticks) == 0:
                        entry_price = row['open']
                    else:
                        first_tick = bar_ticks.iloc[0]
                        entry_price = first_tick['ask']

                    # Margin check (account for SHORT position if open)
                    open_positions = [p for p in [short_position] if p is not None]
                    can_trade, reason = self.margin_validator.can_open_position(entry_price, open_positions)

                    if not can_trade:
                        self.trades_blocked_margin += 1
                        long_entry_signal = False
                    else:
                        long_position = {
                            'trade_type': 'LONG',
                            'entry_price': entry_price,
                            'entry_time': bar_timestamp,
                            'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                            'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                            'tp_level': entry_price + self.long_tp,
                            'sl_level': entry_price - self.long_sl,
                            'tp_pts': self.long_tp,
                            'sl_pts': self.long_sl,
                            'bars_held': 0,
                            'days_held': 0,
                            'overnight_charges_pts': 0.0,
                            'highest_bid': entry_price,
                            'trailing_active': False,
                        }
                        self.logger.debug(f"LONG ENTRY at {bar_timestamp}: {entry_price:.2f}")
                        long_entry_signal = False

            # ===== SHORT ENTRY LOGIC =====
            if self.short_enabled:
                if row['rsi'] >= self.short_overbought:
                    seen_overbought = True

                if (short_position is None and
                    not short_entry_signal and
                    seen_overbought and
                    row['rsi'] < self.short_overbought and
                    row['entry_allowed']):

                    short_entry_signal = True
                    seen_overbought = False

                # Execute SHORT entry on NEXT bar
                elif short_entry_signal and short_position is None:
                    bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

                    if len(bar_ticks) == 0:
                        entry_price = row['open']
                    else:
                        first_tick = bar_ticks.iloc[0]
                        entry_price = first_tick['bid']

                    # Margin check (account for LONG position if open)
                    open_positions = [p for p in [long_position] if p is not None]
                    can_trade, reason = self.margin_validator.can_open_position(entry_price, open_positions)

                    if not can_trade:
                        self.trades_blocked_margin += 1
                        short_entry_signal = False
                    else:
                        short_position = {
                            'trade_type': 'SHORT',
                            'entry_price': entry_price,
                            'entry_time': bar_timestamp,
                            'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                            'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                            'tp_level': entry_price - self.short_tp,
                            'sl_level': entry_price + self.short_sl,
                            'tp_pts': self.short_tp,
                            'sl_pts': self.short_sl,
                            'bars_held': 0,
                            'days_held': 0,
                            'overnight_charges_pts': 0.0,
                            'lowest_ask': entry_price,
                            'trailing_active': False,
                        }
                        self.logger.debug(f"SHORT ENTRY at {bar_timestamp}: {entry_price:.2f}")
                        short_entry_signal = False

            # Get bar ticks once (used by both LONG and SHORT)
            bar_ticks = self.get_ticks_for_bar(ticks_df, bar_timestamp, 30)

            # ===== LONG EXIT LOGIC =====
            if long_position is not None:
                long_position['bars_held'] += 1

                # Track overnight charges
                current_date_check = self.session_clock.localize_timestamp(bar_timestamp).date()
                if current_date_check != long_position['entry_date']:
                    days_diff = (current_date_check - long_position['entry_date']).days
                    if days_diff > long_position['days_held']:
                        nights_to_charge = days_diff - long_position['days_held']
                        charge = self._calculate_overnight_charge(long_position['entry_price'], nights_to_charge)
                        long_position['overnight_charges_pts'] += charge
                        long_position['days_held'] = days_diff

                exit_price = None
                exit_reason = None
                exit_time = bar_timestamp

                # Check max hold days
                if self.long_max_hold_days > 0 and long_position['days_held'] >= self.long_max_hold_days:
                    exit_price = row['close']
                    exit_reason = 'MAX_HOLD_DAYS'

                # Process ticks for LONG exit
                if exit_price is None and len(bar_ticks) > 0:
                    for tick_time, tick in bar_ticks.iterrows():
                        bid = tick['bid']

                        if bid > long_position['highest_bid']:
                            long_position['highest_bid'] = bid

                        if self.long_use_trailing:
                            profit_pts = long_position['highest_bid'] - long_position['entry_price']
                            if profit_pts >= self.long_trailing_activation and not long_position['trailing_active']:
                                long_position['trailing_active'] = True

                            if long_position['trailing_active']:
                                new_sl = long_position['highest_bid'] - self.long_trailing_distance
                                if new_sl > long_position['sl_level']:
                                    long_position['sl_level'] = new_sl

                        if bid <= long_position['sl_level']:
                            exit_price = long_position['sl_level']
                            exit_reason = 'TRAILING_SL' if long_position['trailing_active'] else 'SL'
                            exit_time = tick_time
                            break

                        if bid >= long_position['tp_level']:
                            exit_price = long_position['tp_level']
                            exit_reason = 'TP'
                            exit_time = tick_time
                            break

                # Check EOD exit for LONG
                if exit_price is None and self.long_force_eod:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        if len(bar_ticks) > 0:
                            exit_price = bar_ticks.iloc[-1]['bid']
                        else:
                            exit_price = row['close']
                        exit_reason = 'EOD'

                # Close LONG position
                if exit_price is not None:
                    pnl_pts_gross = exit_price - long_position['entry_price']
                    overnight_charges = long_position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'trade_type': 'LONG',
                        'datetime_open': long_position['entry_time'],
                        'ny_time_open': long_position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': long_position['entry_price'],
                        'tp_pts': long_position['tp_pts'],
                        'sl_pts': long_position['sl_pts'],
                        'datetime_close': exit_time,
                        'ny_time_close': self.session_clock.localize_timestamp(exit_time).strftime('%Y-%m-%d %H:%M:%S'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'pnl_pts': pnl_pts_net,
                        'pnl_pts_gross': pnl_pts_gross,
                        'overnight_charges': overnight_charges,
                        'days_held': long_position['days_held'],
                        'pnl_gbp': pnl_gbp,
                        'bars_held': long_position['bars_held']
                    }

                    self.margin_validator.on_trade_closed(pnl_gbp)
                    trades.append(trade)
                    self.logger.debug(f"LONG EXIT at {exit_time}: {exit_price:.2f} ({exit_reason}) | P&L: {pnl_pts_net:+.2f} pts")
                    long_position = None

            # ===== SHORT EXIT LOGIC =====
            if short_position is not None:
                short_position['bars_held'] += 1

                # Track overnight charges
                current_date_check = self.session_clock.localize_timestamp(bar_timestamp).date()
                if current_date_check != short_position['entry_date']:
                    days_diff = (current_date_check - short_position['entry_date']).days
                    if days_diff > short_position['days_held']:
                        nights_to_charge = days_diff - short_position['days_held']
                        charge = self._calculate_overnight_charge(short_position['entry_price'], nights_to_charge)
                        short_position['overnight_charges_pts'] += charge
                        short_position['days_held'] = days_diff

                exit_price = None
                exit_reason = None
                exit_time = bar_timestamp

                # Check max hold days
                if self.short_max_hold_days > 0 and short_position['days_held'] >= self.short_max_hold_days:
                    exit_price = row['close']
                    exit_reason = 'MAX_HOLD_DAYS'

                # Process ticks for SHORT exit
                if exit_price is None and len(bar_ticks) > 0:
                    for tick_time, tick in bar_ticks.iterrows():
                        ask = tick['ask']

                        if ask < short_position['lowest_ask']:
                            short_position['lowest_ask'] = ask

                        if self.short_use_trailing:
                            profit_pts = short_position['entry_price'] - short_position['lowest_ask']
                            if profit_pts >= self.short_trailing_activation and not short_position['trailing_active']:
                                short_position['trailing_active'] = True

                            if short_position['trailing_active']:
                                new_sl = short_position['lowest_ask'] + self.short_trailing_distance
                                if new_sl < short_position['sl_level']:
                                    short_position['sl_level'] = new_sl

                        if ask >= short_position['sl_level']:
                            exit_price = short_position['sl_level']
                            exit_reason = 'TRAILING_SL' if short_position['trailing_active'] else 'SL'
                            exit_time = tick_time
                            break

                        if ask <= short_position['tp_level']:
                            exit_price = short_position['tp_level']
                            exit_reason = 'TP'
                            exit_time = tick_time
                            break

                # Check EOD exit for SHORT
                if exit_price is None and self.short_force_eod:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        if len(bar_ticks) > 0:
                            exit_price = bar_ticks.iloc[-1]['ask']
                        else:
                            exit_price = row['close']
                        exit_reason = 'EOD'

                # Close SHORT position
                if exit_price is not None:
                    pnl_pts_gross = short_position['entry_price'] - exit_price  # INVERTED
                    overnight_charges = short_position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'trade_type': 'SHORT',
                        'datetime_open': short_position['entry_time'],
                        'ny_time_open': short_position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': short_position['entry_price'],
                        'tp_pts': short_position['tp_pts'],
                        'sl_pts': short_position['sl_pts'],
                        'datetime_close': exit_time,
                        'ny_time_close': self.session_clock.localize_timestamp(exit_time).strftime('%Y-%m-%d %H:%M:%S'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'pnl_pts': pnl_pts_net,
                        'pnl_pts_gross': pnl_pts_gross,
                        'overnight_charges': overnight_charges,
                        'days_held': short_position['days_held'],
                        'pnl_gbp': pnl_gbp,
                        'bars_held': short_position['bars_held']
                    }

                    self.margin_validator.on_trade_closed(pnl_gbp)
                    trades.append(trade)
                    self.logger.debug(f"SHORT EXIT at {exit_time}: {exit_price:.2f} ({exit_reason}) | P&L: {pnl_pts_net:+.2f} pts")
                    short_position = None

        # Sort trades by datetime_open
        trades.sort(key=lambda x: x['datetime_open'])

        self.logger.info("=" * 60)
        self.logger.info(f"BOTH Tick backtest complete: {len(trades)} trades")
        self.logger.info("=" * 60)

        return trades
