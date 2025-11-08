"""Trailing stop manager for dynamic SL updates."""

import logging
from typing import Optional, Dict, Any, Tuple


class TrailingStopManager:
    """
    Manages trailing stop logic for open positions.

    Tracks highest bid reached and updates trailing SL accordingly.
    Works in conjunction with broker API to update SL levels.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize trailing stop manager.

        Args:
            config: Configuration dictionary with trailing stop parameters
        """
        self.config = config
        self.logger = logging.getLogger("rsi2_strategy.trailing_stop")

        # Trailing stop configuration
        self.enabled = config.get('use_trailing_stop', False)
        self.activation_pts = config.get('trailing_stop_activation_pts', 25)
        self.distance_pts = config.get('trailing_stop_distance_pts', 10)

        # Position tracking
        self.position: Optional[Dict[str, Any]] = None
        self.highest_bid: Optional[float] = None
        self.trailing_active: bool = False
        self.current_sl_level: Optional[float] = None

        if self.enabled:
            self.logger.info(f"Trailing stop enabled: activation={self.activation_pts} pts, "
                           f"distance={self.distance_pts} pts")
        else:
            self.logger.info("Trailing stop disabled")

    def is_enabled(self) -> bool:
        """Check if trailing stop is enabled."""
        return self.enabled

    def on_position_opened(self, entry_price: float, tp_level: float, sl_level: float,
                          deal_id: str):
        """
        Initialize tracking for newly opened position.

        Args:
            entry_price: Position entry price
            tp_level: Take profit level (fixed)
            sl_level: Initial stop loss level
            deal_id: Deal ID from broker
        """
        self.position = {
            'entry_price': entry_price,
            'tp_level': tp_level,
            'sl_level': sl_level,
            'deal_id': deal_id
        }
        self.highest_bid = entry_price
        self.trailing_active = False
        self.current_sl_level = sl_level

        self.logger.info(f"Trailing stop initialized: entry={entry_price:.2f}, "
                        f"tp={tp_level:.2f}, initial_sl={sl_level:.2f}")

    def on_tick(self, bid: float) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Process tick and determine if SL needs updating or exit needed.

        Args:
            bid: Current bid price

        Returns:
            Tuple of (should_update_sl, new_sl_level, exit_reason)
            - should_update_sl: True if SL should be updated
            - new_sl_level: New SL level (if should_update_sl is True)
            - exit_reason: None (exits handled by IG, not locally)
        """
        if not self.enabled or not self.position:
            return False, None, None

        # Update highest bid if new high reached
        if bid > self.highest_bid:
            self.highest_bid = bid
            self.logger.debug(f"New highest bid: {self.highest_bid:.2f}")

        # Calculate current profit
        current_profit = self.highest_bid - self.position['entry_price']

        # Check if trailing stop should be activated
        if not self.trailing_active and current_profit >= self.activation_pts:
            self.trailing_active = True
            self.logger.info(f"✓ Trailing stop ACTIVATED! Profit reached {current_profit:.2f} pts "
                           f"(threshold: {self.activation_pts} pts)")

        # Calculate new SL if trailing is active
        if self.trailing_active:
            # New SL = highest bid - distance
            new_sl = self.highest_bid - self.distance_pts

            # Only move SL UP (never down)
            if new_sl > self.current_sl_level:
                self.logger.debug(f"Trailing SL update needed: {self.current_sl_level:.2f} → {new_sl:.2f} "
                                f"(+{new_sl - self.current_sl_level:.2f} pts)")
                self.current_sl_level = new_sl
                return True, new_sl, None

        return False, None, None

    def on_position_closed(self):
        """
        Reset tracking when position closes.
        """
        if self.position:
            self.logger.info(f"Trailing stop reset (position closed)")

        self.position = None
        self.highest_bid = None
        self.trailing_active = False
        self.current_sl_level = None

    def has_position(self) -> bool:
        """Check if currently tracking a position."""
        return self.position is not None

    def get_status(self) -> Dict[str, Any]:
        """
        Get current trailing stop status.

        Returns:
            Status dictionary with current state
        """
        if not self.position:
            return {
                'active': False,
                'position': None
            }

        current_profit = (self.highest_bid - self.position['entry_price']) if self.highest_bid else 0

        return {
            'active': True,
            'trailing_active': self.trailing_active,
            'entry_price': self.position['entry_price'],
            'highest_bid': self.highest_bid,
            'current_profit': current_profit,
            'current_sl': self.current_sl_level,
            'activation_threshold': self.activation_pts,
            'trailing_distance': self.distance_pts
        }

    def restore_position(self, saved_position: Dict[str, Any], current_bid: float):
        """
        Restore position tracking from saved state (crash recovery).

        Recalculates trailing state from current price instead of relying on saved SL.

        Args:
            saved_position: Position dict from trade_state.json
            current_bid: Current market bid price
        """
        entry_price = saved_position['entry_price']
        tp_level = saved_position['tp_level']
        sl_level = saved_position['sl_level']
        deal_id = saved_position['deal_id']

        # Restore position
        self.position = {
            'entry_price': entry_price,
            'tp_level': tp_level,
            'sl_level': sl_level,
            'deal_id': deal_id
        }

        # Recalculate from current price
        current_profit = current_bid - entry_price

        # Determine if trailing should be active
        if current_profit >= self.activation_pts:
            self.trailing_active = True
            self.highest_bid = current_bid
            self.current_sl_level = current_bid - self.distance_pts
            self.logger.warning(f"Restored trailing stop (ACTIVE): "
                              f"current_bid={current_bid:.2f}, "
                              f"profit={current_profit:.2f}, "
                              f"recalculated_sl={self.current_sl_level:.2f}")
        else:
            self.trailing_active = False
            self.highest_bid = entry_price
            self.current_sl_level = sl_level
            self.logger.warning(f"Restored trailing stop (INACTIVE): "
                              f"current_bid={current_bid:.2f}, "
                              f"profit={current_profit:.2f}, "
                              f"original_sl={sl_level:.2f}")
