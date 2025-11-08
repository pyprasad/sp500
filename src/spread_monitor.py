"""Spread monitoring and logging for market spread analysis."""

import csv
import logging
import queue
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional


class SpreadMonitor:
    """
    Monitors and logs BID/OFFER spreads asynchronously.

    Uses background thread to avoid blocking main trading loop.
    Logs spread data to CSV for historical analysis.
    """

    def __init__(self, config: dict, epic: str):
        """
        Initialize spread monitor.

        Args:
            config: Configuration dictionary
            epic: Market EPIC code
        """
        self.logger = logging.getLogger("rsi2_strategy.spread_monitor")
        self.epic = epic

        # Configuration
        self.enabled = config.get('log_spreads', True)
        self.log_interval = config.get('spread_log_interval_sec', 300)  # 5 minutes default
        self.max_entry_spread = config.get('max_entry_spread_pts', 4.0)

        # Spread logging path
        spread_log_dir = Path(config.get('spread_log_path', 'data/spreads'))
        spread_log_dir.mkdir(parents=True, exist_ok=True)
        self.csv_file = spread_log_dir / f"{epic}_spread_log.csv"

        # Thread-safe queue for spread data
        self.spread_queue = queue.Queue()

        # Current spread tracking
        self.current_spread = None
        self.last_logged_spread = None
        self.last_log_time = 0

        # Background writer thread
        self.running = False
        self.writer_thread = None

        if self.enabled:
            self._start_writer_thread()
            self.logger.info(f"Spread monitoring enabled: log_interval={self.log_interval}s, "
                           f"max_entry_spread={self.max_entry_spread} pts")
            self.logger.info(f"Spread log file: {self.csv_file}")
        else:
            self.logger.info("Spread monitoring disabled")

    def _start_writer_thread(self):
        """Start background CSV writer thread."""
        self.running = True
        self.writer_thread = threading.Thread(target=self._csv_writer_loop, daemon=True)
        self.writer_thread.start()

        # Initialize CSV file with headers
        self._initialize_csv()

    def _initialize_csv(self):
        """Create CSV file with headers if it doesn't exist."""
        if not self.csv_file.exists():
            try:
                with open(self.csv_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['timestamp', 'bid', 'offer', 'spread_pts', 'market_open', 'notes'])
                self.logger.info(f"Created spread log: {self.csv_file}")
            except Exception as e:
                self.logger.error(f"Failed to initialize spread log: {e}")

    def on_tick(self, bid: float, ask: float, timestamp: str, is_market_open: bool = True):
        """
        Process tick and update spread monitoring.

        Called from main thread - must be non-blocking!

        Args:
            bid: Current bid price
            ask: Current ask/offer price
            timestamp: Tick timestamp
            is_market_open: Whether market is currently in session
        """
        if not self.enabled:
            return

        spread = ask - bid
        self.current_spread = spread

        current_time = time.time()

        # Check if we should log this tick
        should_log = False
        notes = ""

        # Log at regular intervals
        if (current_time - self.last_log_time) >= self.log_interval:
            should_log = True
            notes = "scheduled_log"

        # Log significant spread changes (>0.5 pts difference)
        elif self.last_logged_spread is not None:
            spread_change = abs(spread - self.last_logged_spread)
            if spread_change > 0.5:
                should_log = True
                notes = f"spread_change_{spread_change:.2f}pts"

        # Log if spread exceeds max entry threshold
        if spread > self.max_entry_spread:
            should_log = True
            notes = f"wide_spread_warning_{spread:.2f}pts"
            self.logger.warning(f"Wide spread detected: {spread:.2f} pts (max: {self.max_entry_spread} pts)")

        # Push to queue if should log (non-blocking)
        if should_log:
            try:
                self.spread_queue.put({
                    'timestamp': timestamp,
                    'bid': bid,
                    'ask': ask,
                    'spread': spread,
                    'market_open': is_market_open,
                    'notes': notes
                }, block=False)

                self.last_log_time = current_time
                self.last_logged_spread = spread

            except queue.Full:
                self.logger.warning("Spread queue full, dropping data point")

    def _csv_writer_loop(self):
        """
        Background thread - periodically flushes queued data to CSV.

        Runs in separate thread to avoid blocking main trading loop.
        """
        self.logger.info("Spread CSV writer thread started")

        while self.running:
            try:
                # Collect queued data
                data_batch = []

                # Non-blocking drain of queue
                while not self.spread_queue.empty():
                    try:
                        data_batch.append(self.spread_queue.get_nowait())
                    except queue.Empty:
                        break

                # Write batch to CSV
                if data_batch:
                    self._write_batch_to_csv(data_batch)

                # Sleep before next check
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"Error in spread writer thread: {e}", exc_info=True)
                time.sleep(5)  # Back off on error

        self.logger.info("Spread CSV writer thread stopped")

    def _write_batch_to_csv(self, data_batch: list):
        """
        Write batch of spread data to CSV.

        Args:
            data_batch: List of spread data dictionaries
        """
        try:
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                for data in data_batch:
                    writer.writerow([
                        data['timestamp'],
                        f"{data['bid']:.2f}",
                        f"{data['ask']:.2f}",
                        f"{data['spread']:.2f}",
                        data['market_open'],
                        data['notes']
                    ])

            self.logger.debug(f"Wrote {len(data_batch)} spread records to CSV")

        except Exception as e:
            self.logger.error(f"Failed to write spread data to CSV: {e}")

    def is_spread_acceptable_for_entry(self, current_spread: Optional[float] = None) -> bool:
        """
        Check if current spread is within acceptable range for entry.

        Args:
            current_spread: Spread to check (uses self.current_spread if None)

        Returns:
            True if spread is acceptable, False if too wide
        """
        if not self.enabled:
            return True  # If monitoring disabled, allow all entries

        spread = current_spread if current_spread is not None else self.current_spread

        if spread is None:
            self.logger.warning("No spread data available for entry check")
            return True  # Allow entry if no data (conservative)

        acceptable = spread <= self.max_entry_spread

        if not acceptable:
            self.logger.warning(f"Entry blocked: spread {spread:.2f} exceeds max {self.max_entry_spread} pts")

        return acceptable

    def get_current_spread(self) -> Optional[float]:
        """Get current spread in points."""
        return self.current_spread

    def stop(self):
        """Stop the spread monitor and flush remaining data."""
        if not self.enabled:
            return

        self.logger.info("Stopping spread monitor...")
        self.running = False

        if self.writer_thread:
            self.writer_thread.join(timeout=5)

        # Flush remaining queued data
        remaining_data = []
        while not self.spread_queue.empty():
            try:
                remaining_data.append(self.spread_queue.get_nowait())
            except queue.Empty:
                break

        if remaining_data:
            self._write_batch_to_csv(remaining_data)
            self.logger.info(f"Flushed {len(remaining_data)} remaining spread records")

        self.logger.info("Spread monitor stopped")
