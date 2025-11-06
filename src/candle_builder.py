"""Build candles from tick data."""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable
import pytz


class CandleBuilder:
    """Builds OHLC candles from tick data."""

    def __init__(self, timeframe_sec: int, output_dir: str = "data/candles"):
        """
        Initialize candle builder.

        Args:
            timeframe_sec: Timeframe in seconds (e.g., 1800 for 30 minutes)
            output_dir: Directory to save candle data
        """
        self.timeframe_sec = timeframe_sec
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("rsi2_strategy.candle_builder")

        # Current candle state
        self.current_candle: Optional[dict] = None
        self.current_candle_start: Optional[datetime] = None

        # Callbacks
        self.on_candle_complete: Optional[Callable] = None

        # Tick file
        self.tick_file = None
        self.tick_writer = None
        self.tick_count = 0

    def set_candle_callback(self, callback: Callable):
        """Set callback for completed candles."""
        self.on_candle_complete = callback

    def start_tick_logging(self, tick_file: str):
        """Start logging ticks to CSV."""
        Path(tick_file).parent.mkdir(parents=True, exist_ok=True)
        self.tick_file = open(tick_file, 'w', newline='')
        self.tick_writer = csv.writer(self.tick_file)
        self.tick_writer.writerow(['timestamp', 'bid', 'ask', 'mid'])
        self.logger.info(f"Started tick logging to {tick_file}")

    def stop_tick_logging(self):
        """Stop tick logging."""
        if self.tick_file:
            self.tick_file.close()
            self.tick_file = None
            self.tick_writer = None

    def process_tick(self, bid: float, ask: float, timestamp: str = None):
        """
        Process incoming tick.

        Args:
            bid: Bid price
            ask: Ask price
            timestamp: Tick timestamp (if None, uses current time)
        """
        # Calculate mid price
        mid = (bid + ask) / 2.0

        # Use current UTC time if no timestamp provided
        if timestamp is None:
            tick_time = datetime.now(pytz.UTC)
        else:
            # Parse IG timestamp format
            try:
                tick_time = datetime.strptime(timestamp, '%H:%M:%S')
                # Add current date
                now = datetime.now(pytz.UTC)
                tick_time = tick_time.replace(
                    year=now.year,
                    month=now.month,
                    day=now.day,
                    tzinfo=pytz.UTC
                )
            except:
                tick_time = datetime.now(pytz.UTC)

        # Log tick
        if self.tick_writer:
            self.tick_count += 1
            self.tick_writer.writerow([
                tick_time.isoformat(),
                bid,
                ask,
                mid
            ])
            self.tick_file.flush()  # Flush immediately to ensure data is written

        # Get candle period start
        period_start = self._get_period_start(tick_time)

        # Initialize or update candle
        if self.current_candle is None or period_start != self.current_candle_start:
            # Complete previous candle if exists
            if self.current_candle is not None:
                self._complete_candle()

            # Start new candle
            self.current_candle = {
                'timestamp': period_start,
                'open': mid,
                'high': mid,
                'low': mid,
                'close': mid,
                'volume': 1
            }
            self.current_candle_start = period_start

        else:
            # Update existing candle
            self.current_candle['high'] = max(self.current_candle['high'], mid)
            self.current_candle['low'] = min(self.current_candle['low'], mid)
            self.current_candle['close'] = mid
            self.current_candle['volume'] += 1

    def _get_period_start(self, dt: datetime) -> datetime:
        """Get start of candle period for given timestamp."""
        # Round down to nearest timeframe boundary
        timestamp = dt.timestamp()
        period_timestamp = (timestamp // self.timeframe_sec) * self.timeframe_sec
        return datetime.fromtimestamp(period_timestamp, tz=pytz.UTC)

    def _complete_candle(self):
        """Complete and emit current candle."""
        if self.current_candle is None:
            return

        self.logger.debug(f"Completed candle: {self.current_candle['timestamp']} "
                         f"O:{self.current_candle['open']:.2f} "
                         f"H:{self.current_candle['high']:.2f} "
                         f"L:{self.current_candle['low']:.2f} "
                         f"C:{self.current_candle['close']:.2f}")

        # Save to file
        self._save_candle(self.current_candle)

        # Call callback
        if self.on_candle_complete:
            self.on_candle_complete(self.current_candle.copy())

    def _save_candle(self, candle: dict):
        """Save candle to CSV file."""
        date_str = candle['timestamp'].strftime('%Y%m%d')
        candle_file = self.output_dir / f"candles_{date_str}.csv"

        # Check if file exists
        file_exists = candle_file.exists()

        with open(candle_file, 'a', newline='') as f:
            writer = csv.writer(f)

            # Write header if new file
            if not file_exists:
                writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Write candle
            writer.writerow([
                candle['timestamp'].isoformat(),
                candle['open'],
                candle['high'],
                candle['low'],
                candle['close'],
                candle['volume']
            ])

    def force_complete_candle(self):
        """Force completion of current candle (e.g., at shutdown)."""
        if self.current_candle is not None:
            self._complete_candle()
            self.current_candle = None
            self.current_candle_start = None
