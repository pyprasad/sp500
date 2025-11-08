"""Persistent trade state management for crash recovery."""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class TradeState:
    """
    Manages persistent trade state for crash recovery.

    State file is only written when:
    - Position opens (save initial state)
    - Position closes (delete file)

    NOT written on every trailing SL update (too frequent, unnecessary).
    """

    def __init__(self, state_file: str = "data/state/trade_state.json"):
        """
        Initialize trade state manager.

        Args:
            state_file: Path to JSON state file (configurable per market)
        """
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("rsi2_strategy.trade_state")

    def save_position(self, position: Dict[str, Any]):
        """
        Save active position to disk.

        Called when:
        - Position opens (initial save)

        NOT called when:
        - Trailing SL updates (too frequent)

        Args:
            position: Position dictionary with all details
        """
        state = {
            'position': position,
            'last_updated': datetime.now().isoformat(),
            'version': '1.0'
        }

        # Atomic write (write to temp file, then rename)
        temp_file = self.state_file.with_suffix('.tmp')

        try:
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)

            # Atomic rename (prevents corruption if crash during write)
            temp_file.replace(self.state_file)

            self.logger.info(f"Trade state saved: deal_id={position.get('deal_id')}")

        except Exception as e:
            self.logger.error(f"Failed to save trade state: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def load_position(self) -> Optional[Dict[str, Any]]:
        """
        Load position from disk on startup.

        Returns:
            Position dict if file exists, None otherwise
        """
        if not self.state_file.exists():
            self.logger.info("No saved position state found")
            return None

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            position = state.get('position')
            last_updated = state.get('last_updated')

            self.logger.warning("=" * 60)
            self.logger.warning("FOUND OPEN POSITION FROM PREVIOUS SESSION")
            self.logger.warning("=" * 60)
            self.logger.warning(f"Deal ID:      {position.get('deal_id')}")
            self.logger.warning(f"Entry Price:  {position.get('entry_price'):.2f}")
            self.logger.warning(f"Entry Time:   {position.get('entry_time')}")
            self.logger.warning(f"Last Updated: {last_updated}")
            self.logger.warning("=" * 60)

            return position

        except Exception as e:
            self.logger.error(f"Failed to load trade state: {e}")
            return None

    def clear_position(self):
        """
        Remove position state when closed.

        Called when:
        - Position closes (TP/SL/manual)
        - Reconciliation finds position no longer exists on IG
        """
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                self.logger.info("Trade state cleared (position closed)")
            except Exception as e:
                self.logger.error(f"Failed to clear trade state: {e}")

    def position_exists(self) -> bool:
        """
        Check if state file exists.

        Returns:
            True if position state file exists
        """
        return self.state_file.exists()

    def get_state_file_path(self) -> Path:
        """Get path to state file."""
        return self.state_file
