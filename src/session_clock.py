"""Session timing and trading hours management."""

from datetime import datetime, time, timedelta
import pytz
from typing import Dict, Any


class SessionClock:
    """Manages trading session timing rules."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize session clock.

        Args:
            config: Configuration dictionary with tz, session_open, session_close, no_trade_first_minutes
        """
        self.tz = pytz.timezone(config.get('tz', 'America/New_York'))
        self.session_open = self._parse_time(config.get('session_open', '09:30'))
        self.session_close = self._parse_time(config.get('session_close', '16:00'))
        self.no_trade_first_minutes = config.get('no_trade_first_minutes', 30)

        # Calculate entry window start time
        entry_start = datetime.combine(datetime.today(), self.session_open)
        entry_start += timedelta(minutes=self.no_trade_first_minutes)
        self.entry_start_time = entry_start.time()

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse time string 'HH:MM' to time object."""
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)

    def localize_timestamp(self, dt: datetime) -> datetime:
        """Convert timestamp to session timezone."""
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(self.tz)

    def is_session_open(self, dt: datetime) -> bool:
        """Check if timestamp is within session hours."""
        dt_local = self.localize_timestamp(dt)
        current_time = dt_local.time()
        return self.session_open <= current_time < self.session_close

    def is_entry_allowed(self, dt: datetime) -> bool:
        """Check if entry is allowed (after initial no-trade period)."""
        dt_local = self.localize_timestamp(dt)
        current_time = dt_local.time()

        # Must be after entry start time and before session close
        return self.entry_start_time <= current_time < self.session_close

    def is_eod_bar(self, dt: datetime, bar_duration_minutes: int = 30) -> bool:
        """
        Check if this is the last bar of the session.

        Args:
            dt: Bar timestamp
            bar_duration_minutes: Bar duration in minutes

        Returns:
            True if this is the last eligible bar before session close
        """
        dt_local = self.localize_timestamp(dt)
        current_time = dt_local.time()

        # Calculate time of next bar
        next_bar_time = (
            datetime.combine(datetime.today(), current_time) +
            timedelta(minutes=bar_duration_minutes)
        ).time()

        # This is EOD bar if next bar would be at or after session close
        return next_bar_time >= self.session_close

    def get_trading_date(self, dt: datetime) -> datetime:
        """Get the trading date (date in session timezone)."""
        dt_local = self.localize_timestamp(dt)
        return dt_local.date()

    def format_time(self, dt: datetime) -> str:
        """Format datetime in session timezone."""
        dt_local = self.localize_timestamp(dt)
        return dt_local.strftime('%Y-%m-%d %H:%M:%S %Z')
