"""Margin requirement validator for position management."""

import logging
from typing import Dict, Any, List, Tuple, Optional


class MarginValidator:
    """
    Validates margin requirements before opening new positions.

    Ensures account has sufficient free margin to cover new trades.
    Uses realized P&L only (not unrealized) for balance calculation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize margin validator.

        Args:
            config: Configuration dictionary
        """
        self.logger = logging.getLogger("rsi2_strategy.margin")

        self.starting_capital = config.get('starting_capital', 10000.0)
        self.margin_requirement_pct = config.get('margin_requirement_pct', 5.0) / 100.0  # Convert to decimal
        self.size_gbp_per_point = config.get('size_gbp_per_point', 2.0)

        # Track realized P&L (closed trades only)
        self.realized_pnl = 0.0

        self.logger.info(f"Margin validator initialized: "
                        f"Capital=£{self.starting_capital:,.2f}, "
                        f"Margin={self.margin_requirement_pct*100:.1f}%, "
                        f"Size={self.size_gbp_per_point} GBP/pt")

    def get_account_balance(self) -> float:
        """
        Get current account balance (starting capital + realized P&L).

        Returns:
            Account balance in GBP
        """
        return self.starting_capital + self.realized_pnl

    def calculate_required_margin(self, entry_price: float) -> float:
        """
        Calculate margin required for a new position.

        Args:
            entry_price: Entry price for the position

        Returns:
            Required margin in GBP
        """
        # Margin = Price × Size × Margin%
        required = entry_price * self.size_gbp_per_point * self.margin_requirement_pct
        return required

    def calculate_used_margin(self, open_positions: List[Dict[str, Any]]) -> float:
        """
        Calculate margin currently used by open positions.

        Args:
            open_positions: List of currently open position dictionaries

        Returns:
            Used margin in GBP
        """
        used = 0.0
        for pos in open_positions:
            entry_price = pos.get('entry_price', 0.0)
            used += entry_price * self.size_gbp_per_point * self.margin_requirement_pct

        return used

    def can_open_position(self, entry_price: float,
                         open_positions: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Check if account has sufficient margin to open new position.

        Args:
            entry_price: Entry price for new position
            open_positions: List of currently open positions

        Returns:
            (can_open, reason): Tuple of bool and explanation string
        """
        # Get current balance (realized P&L only)
        balance = self.get_account_balance()

        # Calculate margin already used
        used_margin = self.calculate_used_margin(open_positions)

        # Calculate margin needed for new position
        required_margin = self.calculate_required_margin(entry_price)

        # Calculate free margin
        free_margin = balance - used_margin

        # Check if sufficient
        if free_margin >= required_margin:
            return True, (f"OK (Balance: £{balance:,.2f}, Free: £{free_margin:,.2f}, "
                         f"Required: £{required_margin:,.2f})")
        else:
            return False, (f"INSUFFICIENT_MARGIN (Balance: £{balance:,.2f}, "
                          f"Free: £{free_margin:,.2f}, Required: £{required_margin:,.2f})")

    def on_trade_closed(self, pnl_gbp: float):
        """
        Update realized P&L when a trade closes.

        Args:
            pnl_gbp: Trade P&L in GBP
        """
        self.realized_pnl += pnl_gbp
        balance = self.get_account_balance()

        self.logger.debug(f"Trade closed: P&L={pnl_gbp:+.2f} GBP, "
                         f"Total Realized={self.realized_pnl:+.2f} GBP, "
                         f"Balance=£{balance:,.2f}")

    def get_status(self, open_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get current margin status.

        Args:
            open_positions: List of currently open positions

        Returns:
            Status dictionary
        """
        balance = self.get_account_balance()
        used_margin = self.calculate_used_margin(open_positions)
        free_margin = balance - used_margin
        margin_level_pct = (balance / used_margin * 100) if used_margin > 0 else 0

        return {
            'balance': balance,
            'starting_capital': self.starting_capital,
            'realized_pnl': self.realized_pnl,
            'used_margin': used_margin,
            'free_margin': free_margin,
            'margin_level_pct': margin_level_pct,
            'open_positions': len(open_positions)
        }
