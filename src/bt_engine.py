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
        self.oversold = config.get('oversold', 3.0)
        self.stop_loss_pts = config.get('stop_loss_pts', 2.0)
        self.spread_pts = config.get('spread_assumption_pts', 0.6)
        self.size_gbp_per_point = config.get('size_gbp_per_point', 1.0)

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

    def run_backtest(self, df: pd.DataFrame, tp_pts: float) -> List[Dict[str, Any]]:
        """
        Run backtest on historical data.

        Args:
            df: DataFrame with OHLCV data
            tp_pts: Take profit in points

        Returns:
            List of trade dictionaries
        """
        # Filter to session bars
        df = self.filter_session_bars(df)

        if len(df) == 0:
            return []

        # Compute RSI
        rsi = compute_rsi(df['close'], self.rsi_period)
        df['rsi'] = rsi

        # Initialize state
        seen_oversold = False
        position = None
        trades = []
        current_date = None

        for idx, row in df.iterrows():
            bar_timestamp = row['timestamp']
            bar_date = self.session_clock.get_trading_date(bar_timestamp)

            # Reset seen_oversold at start of new trading day
            if current_date is None or bar_date != current_date:
                current_date = bar_date
                if position is None:
                    seen_oversold = False

            # Skip if RSI not available
            if pd.isna(row['rsi']):
                continue

            # Check for oversold condition
            if row['rsi'] <= self.oversold:
                seen_oversold = True

            # Entry logic: no position + seen oversold + RSI crosses above threshold + entry allowed
            if (position is None and
                seen_oversold and
                row['rsi'] > self.oversold and
                row['entry_allowed']):

                # Enter at bar open + half spread (ask price)
                entry_price = row['open'] + (self.spread_pts / 2)

                position = {
                    'entry_price': entry_price,
                    'entry_time': bar_timestamp,
                    'entry_time_local': self.session_clock.localize_timestamp(bar_timestamp),
                    'tp_pts': tp_pts,
                    'sl_pts': self.stop_loss_pts,
                    'bars_held': 0
                }

                seen_oversold = False  # Reset after entry

            # Exit logic: check if position exists
            if position is not None:
                position['bars_held'] += 1

                exit_price = None
                exit_reason = None

                # Calculate TP and SL levels
                tp_level = position['entry_price'] + tp_pts
                sl_level = position['entry_price'] - self.stop_loss_pts

                # Check SL first (conservative: SL before TP on same bar)
                if row['low'] <= sl_level:
                    exit_price = sl_level
                    exit_reason = 'SL'
                # Then check TP
                elif row['high'] >= tp_level:
                    exit_price = tp_level
                    exit_reason = 'TP'

                # Check for EOD exit
                is_eod = self.session_clock.is_eod_bar(bar_timestamp, bar_duration_minutes=30)
                if exit_price is None and is_eod:
                    # Exit at close - half spread (bid price)
                    exit_price = row['close'] - (self.spread_pts / 2)
                    exit_reason = 'EOD'

                # Close position if exit triggered
                if exit_price is not None:
                    pnl_pts = exit_price - position['entry_price']
                    pnl_gbp = pnl_pts * self.size_gbp_per_point

                    trade = {
                        'datetime_open': position['entry_time'],
                        'ny_time_open': position['entry_time_local'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': position['entry_price'],
                        'tp_pts': position['tp_pts'],
                        'sl_pts': position['sl_pts'],
                        'datetime_close': bar_timestamp,
                        'ny_time_close': self.session_clock.localize_timestamp(bar_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'pnl_pts': pnl_pts,
                        'pnl_gbp': pnl_gbp,
                        'bars_held': position['bars_held']
                    }

                    trades.append(trade)
                    position = None

        return trades
