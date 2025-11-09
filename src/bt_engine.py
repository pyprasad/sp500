"""Backtest engine core - processes historical candle data."""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional
import pytz
from datetime import datetime

from .indicators import compute_rsi
from .session_clock import SessionClock


class BacktestEngine:
    """Core backtesting engine for RSI-2 strategy."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize backtest engine.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.session_clock = SessionClock(config)
        self.rsi_period = config.get('rsi_period', 2)
        self.spread_pts = config.get('spread_assumption_pts', 0.6)
        self.size_gbp_per_point = config.get('size_gbp_per_point', 1.0)

        # Strategy mode: "long", "short", or "both"
        self.strategy_mode = config.get('strategy_mode', 'long')

        # LONG strategy settings (with fallback to legacy config)
        long_config = config.get('long', {})
        self.long_enabled = long_config.get('enabled', True)  # Default enabled for backward compatibility
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
        self.short_enabled = short_config.get('enabled', False)  # Default disabled
        self.short_overbought = short_config.get('overbought_threshold', 96.0)
        self.short_tp = short_config.get('tp_pts', 40)
        self.short_sl = short_config.get('sl_pts', 80)
        self.short_use_trailing = short_config.get('use_trailing_stop', True)
        self.short_trailing_activation = short_config.get('trailing_activation_pts', 25)
        self.short_trailing_distance = short_config.get('trailing_distance_pts', 10)
        self.short_force_eod = short_config.get('force_eod_exit', False)
        self.short_max_hold_days = short_config.get('max_hold_days', 0)

        # Legacy settings (keep for backward compatibility with old code)
        self.oversold = self.long_oversold
        self.stop_loss_pts = self.long_sl
        self.use_trailing_stop = self.long_use_trailing
        self.trailing_stop_distance = self.long_trailing_distance
        self.trailing_stop_activation = self.long_trailing_activation
        self.force_eod_exit = self.long_force_eod
        self.max_hold_days = self.long_max_hold_days

        # Overnight funding configuration
        self.overnight_funding_rate = config.get('overnight_funding_rate_pct', 0.035)
        self.off_hours_spread_mult = config.get('off_hours_spread_multiplier', 2.5)

        # Margin validator
        from .margin_validator import MarginValidator
        self.margin_validator = MarginValidator(config)

        # Stats tracking
        self.trades_blocked_margin = 0

    def load_data(self, data_path: str) -> pd.DataFrame:
        """
        Load CSV data from file or directory.

        Args:
            data_path: Path to CSV file or directory containing CSVs

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        path = Path(data_path)
        dfs = []

        if path.is_file():
            df = pd.read_csv(path)
            dfs.append(df)
        elif path.is_dir():
            csv_files = sorted(path.glob('*.csv'))
            for csv_file in csv_files:
                # Skip tick data files (they contain 'full' in filename)
                if 'full' in csv_file.name.lower() or 'tick' in csv_file.name.lower():
                    continue
                df = pd.read_csv(csv_file)
                dfs.append(df)
        else:
            raise ValueError(f"Invalid data path: {data_path}")

        if not dfs:
            raise ValueError(f"No CSV files found in {data_path}")

        # Concatenate all dataframes
        df = pd.concat(dfs, ignore_index=True)

        # Normalize column names to lowercase
        df.columns = df.columns.str.lower()

        # Map common column name variations
        column_mapping = {
            'datetime': 'timestamp',
            'date': 'timestamp',
            'time': 'timestamp'
        }
        df.rename(columns=column_mapping, inplace=True)

        # Ensure required columns exist (volume is optional)
        required_cols = ['timestamp', 'open', 'high', 'low', 'close']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Add volume column if missing (set to 0)
        if 'volume' not in df.columns:
            df['volume'] = 0

        # Parse timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    def filter_session_bars(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter dataframe to only include bars within session hours.

        Args:
            df: Input dataframe with timestamp column

        Returns:
            Filtered dataframe with session bars only
        """
        df = df.copy()

        # Localize timestamps
        df['timestamp_local'] = df['timestamp'].apply(self.session_clock.localize_timestamp)

        # Filter to session hours
        df['in_session'] = df['timestamp'].apply(self.session_clock.is_session_open)
        df = df[df['in_session']].copy()

        # Add entry allowed flag
        df['entry_allowed'] = df['timestamp'].apply(self.session_clock.is_entry_allowed)

        return df.reset_index(drop=True)

    def _calculate_overnight_charge(self, entry_price: float, days_held: int) -> float:
        """
        Calculate overnight funding charge.

        Formula: (Price × Annual_Rate × Days) / 365

        Args:
            entry_price: Position entry price
            days_held: Number of nights held

        Returns:
            Funding charge in points
        """
        if days_held == 0:
            return 0.0

        daily_rate = self.overnight_funding_rate / 365.0
        charge_pts = entry_price * daily_rate * days_held
        return charge_pts

    def _get_spread_for_time(self, timestamp: datetime) -> float:
        """
        Get spread based on time (market hours vs off-hours).

        Args:
            timestamp: Bar timestamp

        Returns:
            Spread in points
        """
        if self.session_clock.is_session_open(timestamp):
            return self.spread_pts  # Normal market hours spread
        else:
            return self.spread_pts * self.off_hours_spread_mult  # Wider off-hours spread

    def run_backtest(self, df: pd.DataFrame, tp_pts: float) -> List[Dict[str, Any]]:
        """
        Run backtest on historical data with REALISTIC modeling.

        Supports LONG-only, SHORT-only, or BOTH strategies based on strategy_mode.

        Key realistic assumptions:
        1. NO LOOK-AHEAD BIAS: Entry at NEXT bar's open (after RSI signal on current bar close)
        2. PROPER SPREAD: Entry at ask (mid + spread/2), exits at bid (mid - spread/2)
        3. TP/SL checks against bid prices: high - spread/2 for TP, low - spread/2 for SL

        Args:
            df: DataFrame with OHLCV data
            tp_pts: Take profit in points (DEPRECATED - uses long.tp_pts or short.tp_pts from config)

        Returns:
            List of trade dictionaries
        """
        # Route to appropriate backtest based on strategy_mode and enabled flags
        if self.strategy_mode == "long":
            if not self.long_enabled:
                # LONG disabled - return empty trades
                return []
            return self._run_backtest_long(df)
        elif self.strategy_mode == "short":
            if not self.short_enabled:
                # SHORT disabled - return empty trades
                return []
            return self._run_backtest_short(df)
        elif self.strategy_mode == "both":
            # Check if at least one is enabled
            if not self.long_enabled and not self.short_enabled:
                return []
            return self._run_backtest_both(df)
        else:
            raise ValueError(f"Invalid strategy_mode: {self.strategy_mode}. Must be 'long', 'short', or 'both'")

    def _run_backtest_long(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run LONG-only backtest (RSI oversold rebound).

        This is the original strategy logic, preserved for backward compatibility.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            List of trade dictionaries
        """
        # Filter to session bars
        df = self.filter_session_bars(df)

        if len(df) == 0:
            return []

        # Compute RSI on close prices
        rsi = compute_rsi(df['close'], self.rsi_period)
        df['rsi'] = rsi

        # Initialize state
        seen_oversold = False
        position = None
        trades = []
        current_date = None
        entry_signal = False  # Signal to enter on NEXT bar

        for idx, row in df.iterrows():
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

            # === ENTRY LOGIC ===
            # Check for oversold condition (RSI <= threshold)
            if row['rsi'] <= self.long_oversold:
                seen_oversold = True

            # Detect entry signal: RSI crosses above threshold after being oversold
            # Signal is generated at bar CLOSE (when RSI is calculated)
            if (position is None and
                not entry_signal and
                seen_oversold and
                row['rsi'] > self.long_oversold and
                row['entry_allowed']):

                # Mark entry signal for NEXT bar
                entry_signal = True
                seen_oversold = False  # Reset after signal

            # Execute entry on NEXT bar (realistic: no look-ahead)
            elif entry_signal and position is None:
                # Check margin before entry
                entry_price = row['open'] + (self.spread_pts / 2)
                can_trade, reason = self.margin_validator.can_open_position(entry_price, [])

                if not can_trade:
                    self.trades_blocked_margin += 1
                    entry_signal = False
                    continue

                position = {
                    'trade_type': 'LONG',
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                    'tp_pts': self.long_tp,
                    'sl_pts': self.long_sl,
                    'bars_held': 0,
                    'days_held': 0,
                    'overnight_charges_pts': 0.0,
                    'highest_bid': entry_price,
                    'trailing_stop_active': False,
                    'trailing_sl_level': entry_price - self.long_sl
                }

                entry_signal = False  # Reset signal

            # === EXIT LOGIC ===
            if position is not None:
                position['bars_held'] += 1

                # Track overnight holds and charges
                current_date = self.session_clock.localize_timestamp(bar_timestamp).date()
                if current_date != position['entry_date']:
                    # Day changed - calculate days held
                    days_diff = (current_date - position['entry_date']).days
                    if days_diff > position['days_held']:
                        # New overnight period - calculate charges
                        nights_to_charge = days_diff - position['days_held']
                        charge = self._calculate_overnight_charge(position['entry_price'], nights_to_charge)
                        position['overnight_charges_pts'] += charge
                        position['days_held'] = days_diff

                # Initialize exit variables
                exit_price = None
                exit_reason = None

                # Check max hold days limit (if set)
                if self.long_max_hold_days > 0 and position['days_held'] >= self.long_max_hold_days:
                    # Force exit due to max hold period
                    exit_price = row['close'] - (self.spread_pts / 2)
                    exit_reason = 'MAX_HOLD_DAYS'

                # Get current spread (may be wider during off-hours)
                current_spread = self._get_spread_for_time(bar_timestamp)

                # Get bid prices from bar high/low (mid - spread/2)
                # Use current spread instead of fixed spread
                bid_high = row['high'] - (current_spread / 2)
                bid_low = row['low'] - (current_spread / 2)

                # Calculate TP level (fixed)
                tp_level = position['entry_price'] + self.long_tp

                # Update highest bid reached (for trailing stop)
                if bid_high > position['highest_bid']:
                    position['highest_bid'] = bid_high

                # Trailing stop logic (only if enabled in config)
                if self.long_use_trailing:
                    # Calculate profit so far
                    current_profit = position['highest_bid'] - position['entry_price']

                    # Activate trailing stop if profit threshold reached
                    if not position['trailing_stop_active'] and current_profit >= self.long_trailing_activation:
                        position['trailing_stop_active'] = True

                    # Update trailing SL if active
                    if position['trailing_stop_active']:
                        # Trailing SL = highest_bid - trailing_distance
                        new_trailing_sl = position['highest_bid'] - self.long_trailing_distance
                        # Only move SL up, never down
                        if new_trailing_sl > position['trailing_sl_level']:
                            position['trailing_sl_level'] = new_trailing_sl
                else:
                    # Fixed SL (original behavior)
                    position['trailing_sl_level'] = position['entry_price'] - self.long_sl

                # Current SL level (trailing or fixed)
                sl_level = position['trailing_sl_level']

                # Check SL first (conservative: SL before TP if both hit same bar)
                # SL hit if bid_low <= sl_level
                if bid_low <= sl_level:
                    exit_price = sl_level
                    exit_reason = 'TRAILING_SL' if (self.long_use_trailing and position['trailing_stop_active']) else 'SL'
                # Then check TP: TP hit if bid_high >= tp_level
                elif bid_high >= tp_level:
                    exit_price = tp_level
                    exit_reason = 'TP'

                # Check for EOD exit (respects force_eod_exit flag)
                if exit_price is None and self.long_force_eod:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        # Exit at close - half spread (bid price)
                        # Use current spread (may be wider at EOD)
                        exit_price = row['close'] - (current_spread / 2)
                        exit_reason = 'EOD'

                # Close position if exit triggered
                if exit_price is not None:
                    # Calculate P&L before overnight charges
                    pnl_pts_gross = exit_price - position['entry_price']

                    # Subtract overnight charges from P&L
                    overnight_charges = position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'trade_type': position['trade_type'],  # LONG
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': position['tp_pts'],
                        'sl_pts': position['sl_pts'],
                        'datetime_close': bar_timestamp,
                        'ny_time_close': self.session_clock.localize_timestamp(bar_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'pnl_pts': pnl_pts_net,  # Net P&L after overnight charges
                        'pnl_pts_gross': pnl_pts_gross,  # Gross P&L before charges
                        'overnight_charges': overnight_charges,  # Overnight funding charges
                        'days_held': position['days_held'],  # Days position was held
                        'pnl_gbp': pnl_gbp,
                        'bars_held': position['bars_held']
                    }

                    # Update margin validator with realized P&L
                    self.margin_validator.on_trade_closed(pnl_gbp)

                    trades.append(trade)
                    position = None

        return trades

    def _run_backtest_short(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run SHORT-only backtest (RSI overbought rebound).

        SHORT strategy: Enter when RSI crosses DOWN from overbought level.
        P&L is INVERTED: profit when price goes DOWN.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            List of trade dictionaries
        """
        # Filter to session bars
        df = self.filter_session_bars(df)

        if len(df) == 0:
            return []

        # Compute RSI on close prices
        rsi = compute_rsi(df['close'], self.rsi_period)
        df['rsi'] = rsi

        # Initialize state
        seen_overbought = False
        position = None
        trades = []
        current_date = None
        entry_signal = False

        for idx, row in df.iterrows():
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

            # === ENTRY LOGIC (INVERTED from LONG) ===
            # Check for overbought condition (RSI >= threshold)
            if row['rsi'] >= self.short_overbought:
                seen_overbought = True

            # Detect entry signal: RSI crosses BELOW threshold after being overbought
            if (position is None and
                not entry_signal and
                seen_overbought and
                row['rsi'] < self.short_overbought and
                row['entry_allowed']):

                entry_signal = True
                seen_overbought = False

            # Execute entry on NEXT bar
            elif entry_signal and position is None:
                # SHORT enters at BID (sell at current price)
                entry_price = row['open'] - (self.spread_pts / 2)
                can_trade, reason = self.margin_validator.can_open_position(entry_price, [])

                if not can_trade:
                    self.trades_blocked_margin += 1
                    entry_signal = False
                    continue

                position = {
                    'trade_type': 'SHORT',
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'entry_date': self.session_clock.localize_timestamp(bar_timestamp).date(),
                    'tp_pts': self.short_tp,
                    'sl_pts': self.short_sl,
                    'bars_held': 0,
                    'days_held': 0,
                    'overnight_charges_pts': 0.0,
                    'lowest_ask': entry_price,  # Track LOWEST price for SHORT (opposite of LONG)
                    'trailing_stop_active': False,
                    'trailing_sl_level': entry_price + self.short_sl  # SL is ABOVE entry for SHORT
                }

                entry_signal = False

            # === EXIT LOGIC (INVERTED from LONG) ===
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

                # Initialize exit variables
                exit_price = None
                exit_reason = None

                # Check max hold days
                if self.short_max_hold_days > 0 and position['days_held'] >= self.short_max_hold_days:
                    exit_price = row['close'] + (self.spread_pts / 2)  # Exit at ASK for SHORT
                    exit_reason = 'MAX_HOLD_DAYS'

                # Get current spread
                current_spread = self._get_spread_for_time(bar_timestamp)

                # Get ASK prices from bar high/low (SHORT uses ASK for exits)
                ask_high = row['high'] + (current_spread / 2)
                ask_low = row['low'] + (current_spread / 2)

                # Calculate TP and SL levels (INVERTED for SHORT)
                tp_level = position['entry_price'] - self.short_tp  # TP is BELOW entry (price goes down)

                # Update LOWEST ask reached (for trailing stop)
                if ask_low < position['lowest_ask']:
                    position['lowest_ask'] = ask_low

                # Trailing stop logic (INVERTED for SHORT)
                if self.short_use_trailing:
                    # Calculate profit (price went DOWN)
                    current_profit = position['entry_price'] - position['lowest_ask']

                    # Activate trailing stop if profit threshold reached
                    if not position['trailing_stop_active'] and current_profit >= self.short_trailing_activation:
                        position['trailing_stop_active'] = True

                    # Update trailing SL if active (SL trails DOWN for SHORT)
                    if position['trailing_stop_active']:
                        # Trailing SL = lowest_ask + trailing_distance (ABOVE price)
                        new_trailing_sl = position['lowest_ask'] + self.short_trailing_distance
                        # Only move SL DOWN, never up (for SHORT)
                        if new_trailing_sl < position['trailing_sl_level']:
                            position['trailing_sl_level'] = new_trailing_sl
                else:
                    # Fixed SL (original behavior)
                    position['trailing_sl_level'] = position['entry_price'] + self.short_sl

                # Current SL level
                sl_level = position['trailing_sl_level']

                # Check SL first (price went UP - bad for SHORT)
                if ask_high >= sl_level:
                    exit_price = sl_level
                    exit_reason = 'TRAILING_SL' if (self.short_use_trailing and position['trailing_stop_active']) else 'SL'
                # Check TP (price went DOWN - good for SHORT)
                elif ask_low <= tp_level:
                    exit_price = tp_level
                    exit_reason = 'TP'

                # Check EOD exit
                if exit_price is None and self.short_force_eod:
                    is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                    if is_eod:
                        exit_price = row['close'] + (current_spread / 2)  # Exit at ASK
                        exit_reason = 'EOD'

                # Close position if exit triggered
                if exit_price is not None:
                    # Calculate P&L (INVERTED for SHORT: profit when price goes down)
                    pnl_pts_gross = position['entry_price'] - exit_price  # INVERTED

                    # Subtract overnight charges
                    overnight_charges = position['overnight_charges_pts']
                    pnl_pts_net = pnl_pts_gross - overnight_charges
                    pnl_gbp = pnl_pts_net * self.size_gbp_per_point

                    trade = {
                        'trade_type': position['trade_type'],  # SHORT
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': position['tp_pts'],
                        'sl_pts': position['sl_pts'],
                        'datetime_close': bar_timestamp,
                        'ny_time_close': self.session_clock.localize_timestamp(bar_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
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
                    position = None

        return trades

    def _run_backtest_both(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run BOTH LONG and SHORT strategies simultaneously.
        Tracks two separate positions (1 LONG + 1 SHORT).
        Margin validation accounts for both open positions.
        """
        # Filter to session bars (adds entry_allowed flag)
        df = self.filter_session_bars(df)

        if len(df) == 0:
            return []

        # Compute RSI indicator
        rsi = compute_rsi(df['close'], self.rsi_period)
        df['rsi'] = rsi

        # Initialize state
        trades = []
        long_position = None
        short_position = None
        seen_oversold = False  # For LONG entry
        seen_overbought = False  # For SHORT entry
        long_entry_signal = False
        short_entry_signal = False

        for idx, row in df.iterrows():
            bar_timestamp = row['timestamp']

            # Skip if RSI not available
            if pd.isna(row['rsi']):
                continue

            # Get current spread (may be wider during off-hours)
            current_spread = self._get_spread_for_time(bar_timestamp)

            # Calculate BID/ASK for entries (using entry spread)
            bid = row['open'] - (self.spread_pts / 2)
            ask = row['open'] + (self.spread_pts / 2)

            # Calculate BID/ASK for exits (using current spread, may be wider)
            bid_high = row['high'] - (current_spread / 2)
            bid_low = row['low'] - (current_spread / 2)
            ask_high = row['high'] + (current_spread / 2)
            ask_low = row['low'] + (current_spread / 2)

            # ===== LONG STRATEGY LOGIC =====
            if self.long_enabled:
                # LONG entry signal detection
                if row['rsi'] <= self.long_oversold:
                    seen_oversold = True

                # Detect entry signal: RSI crosses above threshold after being oversold
                if (long_position is None and
                    not long_entry_signal and
                    seen_oversold and
                    row['rsi'] > self.long_oversold and
                    row['entry_allowed']):
                    long_entry_signal = True
                    seen_oversold = False

                # LONG entry (execute on next bar after signal)
                elif long_entry_signal and long_position is None:
                    entry_price = ask

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
                            'tp_pts': self.long_tp,
                            'sl_pts': self.long_sl,
                            'bars_held': 0,
                            'highest_bid': bid,
                            'trailing_stop_active': False,
                            'trailing_sl_level': entry_price - self.long_sl,
                            'overnight_charges_pts': 0.0,
                            'days_held': 0
                        }
                        long_entry_signal = False

                # LONG position management
                if long_position is not None:
                    long_position['bars_held'] += 1

                    # Update overnight charges
                    days_since_entry = (bar_timestamp - long_position['entry_time']).total_seconds() / 86400
                    long_position['days_held'] = days_since_entry
                    long_position['overnight_charges_pts'] = (
                        long_position['entry_price'] *
                        self.overnight_funding_rate *
                        days_since_entry / 365
                    )

                    # Update trailing stop
                    if bid_high > long_position['highest_bid']:
                        long_position['highest_bid'] = bid_high

                    if self.long_use_trailing:
                        profit_pts = long_position['highest_bid'] - long_position['entry_price']
                        if profit_pts >= self.long_trailing_activation and not long_position['trailing_stop_active']:
                            long_position['trailing_stop_active'] = True

                        if long_position['trailing_stop_active']:
                            new_trailing_sl = long_position['highest_bid'] - self.long_trailing_distance
                            if new_trailing_sl > long_position['trailing_sl_level']:
                                long_position['trailing_sl_level'] = new_trailing_sl

                    # LONG exit checks
                    exit_price = None
                    exit_reason = None

                    sl_level = long_position['trailing_sl_level']
                    tp_level = long_position['entry_price'] + self.long_tp

                    # Check SL first (conservative)
                    if bid_low <= sl_level:
                        exit_price = sl_level
                        exit_reason = 'TRAILING_SL' if long_position['trailing_stop_active'] else 'SL'
                    elif bid_high >= tp_level:
                        exit_price = tp_level
                        exit_reason = 'TP'

                    # Check EOD exit
                    if exit_price is None and self.long_force_eod:
                        is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                        if is_eod:
                            exit_price = row['close'] - (current_spread / 2)
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
                            'datetime_close': bar_timestamp,
                            'ny_time_close': self.session_clock.localize_timestamp(bar_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
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
                        long_position = None

            # ===== SHORT STRATEGY LOGIC =====
            if self.short_enabled:
                # SHORT entry signal detection
                if row['rsi'] >= self.short_overbought:
                    seen_overbought = True

                # Detect entry signal: RSI crosses below threshold after being overbought
                if (short_position is None and
                    not short_entry_signal and
                    seen_overbought and
                    row['rsi'] < self.short_overbought and
                    row['entry_allowed']):
                    short_entry_signal = True
                    seen_overbought = False

                # SHORT entry (execute on next bar after signal)
                elif short_entry_signal and short_position is None:
                    entry_price = bid

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
                            'tp_pts': self.short_tp,
                            'sl_pts': self.short_sl,
                            'bars_held': 0,
                            'lowest_ask': ask,
                            'trailing_stop_active': False,
                            'trailing_sl_level': entry_price + self.short_sl,
                            'overnight_charges_pts': 0.0,
                            'days_held': 0
                        }
                        short_entry_signal = False

                # SHORT position management
                if short_position is not None:
                    short_position['bars_held'] += 1

                    # Update overnight charges
                    days_since_entry = (bar_timestamp - short_position['entry_time']).total_seconds() / 86400
                    short_position['days_held'] = days_since_entry
                    short_position['overnight_charges_pts'] = (
                        short_position['entry_price'] *
                        self.overnight_funding_rate *
                        days_since_entry / 365
                    )

                    # Update trailing stop
                    if ask_low < short_position['lowest_ask']:
                        short_position['lowest_ask'] = ask_low

                    if self.short_use_trailing:
                        profit_pts = short_position['entry_price'] - short_position['lowest_ask']
                        if profit_pts >= self.short_trailing_activation and not short_position['trailing_stop_active']:
                            short_position['trailing_stop_active'] = True

                        if short_position['trailing_stop_active']:
                            new_trailing_sl = short_position['lowest_ask'] + self.short_trailing_distance
                            if new_trailing_sl < short_position['trailing_sl_level']:
                                short_position['trailing_sl_level'] = new_trailing_sl

                    # SHORT exit checks
                    exit_price = None
                    exit_reason = None

                    sl_level = short_position['trailing_sl_level']
                    tp_level = short_position['entry_price'] - self.short_tp

                    # Check SL first (conservative)
                    if ask_high >= sl_level:
                        exit_price = sl_level
                        exit_reason = 'TRAILING_SL' if short_position['trailing_stop_active'] else 'SL'
                    elif ask_low <= tp_level:
                        exit_price = tp_level
                        exit_reason = 'TP'

                    # Check EOD exit
                    if exit_price is None and self.short_force_eod:
                        is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                        if is_eod:
                            exit_price = row['close'] + (current_spread / 2)
                            exit_reason = 'EOD'

                    # Close SHORT position
                    if exit_price is not None:
                        pnl_pts_gross = short_position['entry_price'] - exit_price
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
                            'datetime_close': bar_timestamp,
                            'ny_time_close': self.session_clock.localize_timestamp(bar_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
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
                        short_position = None

        # Sort trades by datetime_open
        trades.sort(key=lambda x: x['datetime_open'])
        return trades
