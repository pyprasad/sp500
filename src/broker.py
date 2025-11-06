"""Broker interface for IG API order execution."""

import logging
import requests
from typing import Dict, Any, Optional

from .ig_auth import IGAuth


class IGBroker:
    """Handles order execution via IG API."""

    def __init__(self, auth: IGAuth, config: Dict[str, Any]):
        """
        Initialize broker.

        Args:
            auth: IGAuth instance
            config: Configuration dictionary
        """
        self.auth = auth
        self.config = config
        self.logger = logging.getLogger("rsi2_strategy.broker")

        self.epic = config.get('epic')
        self.size = config.get('size_gbp_per_point', 1.0)
        self.dry_run = config.get('dry_run', True)

    def open_position(self, direction: str, entry_price: float,
                     stop_level: float, limit_level: float) -> Optional[str]:
        """
        Open a new position.

        Args:
            direction: BUY or SELL
            entry_price: Entry price for reference
            stop_level: Stop loss level
            limit_level: Take profit level

        Returns:
            Deal reference or None
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would open {direction} position: "
                           f"size={self.size}, stop={stop_level:.2f}, limit={limit_level:.2f}")
            return "DRY_RUN_DEAL_REF"

        if not self.auth.ensure_authenticated():
            self.logger.error("Not authenticated, cannot open position")
            return None

        url = f"{self.auth.base_url}/positions/otc"
        headers = self.auth.get_headers()
        headers['Version'] = '2'

        payload = {
            "epic": self.epic,
            "expiry": "DFB",  # Daily funded bet
            "direction": direction,
            "size": self.size,
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
            "guaranteedStop": False,
            "stopLevel": stop_level,
            "limitLevel": limit_level,
            "forceOpen": True
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            deal_ref = data.get('dealReference')

            self.logger.info(f"Position opened: {direction} {self.size} @ market, "
                           f"stop={stop_level:.2f}, limit={limit_level:.2f}, "
                           f"deal_ref={deal_ref}")

            return deal_ref

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to open position: {e}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Response: {e.response.text}")
            return None

    def close_position(self, deal_id: str, direction: str, size: float) -> bool:
        """
        Close an existing position.

        Args:
            deal_id: Deal ID to close
            direction: BUY or SELL (opposite of original position)
            size: Position size

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would close position: deal_id={deal_id}")
            return True

        if not self.auth.ensure_authenticated():
            self.logger.error("Not authenticated, cannot close position")
            return False

        url = f"{self.auth.base_url}/positions/otc"
        headers = self.auth.get_headers()
        headers['Version'] = '1'
        headers['_method'] = 'DELETE'

        payload = {
            "dealId": deal_id,
            "direction": direction,
            "size": size,
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            self.logger.info(f"Position closed: deal_id={deal_id}")
            return True

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to close position: {e}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Response: {e.response.text}")
            return False

    def get_current_price(self) -> Optional[Dict[str, float]]:
        """
        Get current bid/ask prices.

        Returns:
            Dict with 'bid' and 'ask' keys
        """
        if not self.auth.ensure_authenticated():
            return None

        url = f"{self.auth.base_url}/markets/{self.epic}"
        headers = self.auth.get_headers()
        headers['Version'] = '3'

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            snapshot = data.get('snapshot', {})

            return {
                'bid': float(snapshot.get('bid', 0)),
                'ask': float(snapshot.get('offer', 0))
            }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get current price: {e}")
            return None
