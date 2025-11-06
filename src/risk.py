"""Risk management - position sizing and exit levels."""

import logging
from typing import Dict, Any


class RiskManager:
    """Manages position risk and exit levels."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize risk manager.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("rsi2_strategy.risk")

        self.stop_loss_pts = config.get('stop_loss_pts', 2.0)
        self.spread_pts = config.get('spread_assumption_pts', 0.6)

    def calculate_entry_price(self, bid: float, ask: float, direction: str = 'BUY') -> float:
        """
        Calculate entry price including spread.

        Args:
            bid: Bid price
            ask: Ask price
            direction: BUY or SELL

        Returns:
            Entry price
        """
        if direction == 'BUY':
            return ask
        else:
            return bid

    def calculate_exit_levels(self, entry_price: float, tp_pts: float,
                             direction: str = 'BUY') -> Dict[str, float]:
        """
        Calculate stop loss and take profit levels.

        Args:
            entry_price: Entry price
            tp_pts: Take profit in points
            direction: BUY or SELL

        Returns:
            Dict with 'stop_level' and 'limit_level'
        """
        if direction == 'BUY':
            stop_level = entry_price - self.stop_loss_pts
            limit_level = entry_price + tp_pts
        else:
            stop_level = entry_price + self.stop_loss_pts
            limit_level = entry_price - tp_pts

        return {
            'stop_level': stop_level,
            'limit_level': limit_level
        }

    def check_exit(self, position: Dict[str, Any], current_bid: float,
                  current_ask: float) -> tuple[bool, str]:
        """
        Check if position should be exited based on current prices.

        Args:
            position: Position dict with tp_level and sl_level
            current_bid: Current bid price
            current_ask: Current ask price

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        # For long positions, check bid price for exits
        tp_level = position.get('tp_level')
        sl_level = position.get('sl_level')

        # Check stop loss
        if current_bid <= sl_level:
            return True, 'SL'

        # Check take profit
        if current_bid >= tp_level:
            return True, 'TP'

        return False, None

    def get_position_pnl(self, entry_price: float, current_price: float,
                        direction: str = 'BUY') -> float:
        """
        Calculate current P&L for position.

        Args:
            entry_price: Entry price
            current_price: Current price (bid)
            direction: BUY or SELL

        Returns:
            P&L in points
        """
        if direction == 'BUY':
            return current_price - entry_price
        else:
            return entry_price - current_price
