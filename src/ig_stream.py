"""Lightstreamer client for IG streaming data."""

import logging
from typing import Callable, Optional
from lightstreamer.client import LightstreamerClient, Subscription


class IGStream:
    """Manages Lightstreamer connection for IG tick data."""

    def __init__(self, epic: str, account_id: str, cst: str, x_security: str, ls_endpoint: str = None):
        """
        Initialize Lightstreamer client.

        Args:
            epic: IG instrument epic code
            account_id: IG account ID
            cst: CST token
            x_security: X-SECURITY-TOKEN
            ls_endpoint: Lightstreamer endpoint from /session API
        """
        self.epic = epic
        self.account_id = account_id
        self.logger = logging.getLogger("rsi2_strategy.ig_stream")

        # Use provided endpoint or fallback to hardcoded (should never fallback)
        if not ls_endpoint:
            self.logger.warning("No Lightstreamer endpoint provided, using fallback URL")
            self.ls_endpoint = "https://demo-apd.marketdatasys.com"
        else:
            self.ls_endpoint = ls_endpoint

        self.logger.info(f"Using Lightstreamer endpoint: {self.ls_endpoint}")

        # Setup client
        self.client = LightstreamerClient(self.ls_endpoint, "DEFAULT")

        # Add authentication headers
        self.client.connectionDetails.setUser(account_id)
        self.client.connectionDetails.setPassword(f"CST-{cst}|XST-{x_security}")

        # Add connection status listener
        self._add_connection_listener()

        # Subscriptions
        self.market_subscription: Optional[Subscription] = None
        self.trade_subscription: Optional[Subscription] = None
        self.tick_callback: Optional[Callable] = None
        self.position_callback: Optional[Callable] = None

    def _add_connection_listener(self):
        """Add listener to monitor connection status."""
        class ConnectionListener:
            def __init__(self, logger):
                self.logger = logger

            def onStatusChange(self, status):
                self.logger.info(f"Lightstreamer connection status: {status}")

            def onServerError(self, error_code, error_message):
                self.logger.error(f"Lightstreamer server error {error_code}: {error_message}")

            def onPropertyChange(self, property_name):
                self.logger.debug(f"Lightstreamer property changed: {property_name}")

        self.client.addListener(ConnectionListener(self.logger))

    def subscribe_ticks(self, callback: Callable):
        """
        Subscribe to tick data.

        Args:
            callback: Function to call with tick updates (bid, ask, timestamp)
        """
        self.tick_callback = callback

        # Create subscription for MARKET data
        items = [f"MARKET:{self.epic}"]
        fields = ["BID", "OFFER", "UPDATE_TIME"]

        self.market_subscription = Subscription(
            mode="MERGE",
            items=items,
            fields=fields
        )

        # Set up listener
        self.market_subscription.addListener(self._create_tick_listener())

        # Subscribe
        self.client.subscribe(self.market_subscription)
        self.logger.info(f"Subscribed to {self.epic} tick data")

    def _create_tick_listener(self):
        """Create tick subscription listener."""

        class TickListener:
            def __init__(self, callback, logger):
                self.callback = callback
                self.logger = logger
                self.tick_count = 0

            def onItemUpdate(self, update):
                """Handle item update."""
                try:
                    bid = update.getValue("BID")
                    ask = update.getValue("OFFER")
                    timestamp = update.getValue("UPDATE_TIME")

                    self.tick_count += 1

                    # Log every 100 ticks to confirm data flow
                    if self.tick_count % 100 == 0:
                        self.logger.info(f"Received {self.tick_count} ticks")

                    # Debug log individual ticks
                    self.logger.debug(f"Tick #{self.tick_count}: BID={bid} OFFER={ask} TIME={timestamp}")

                    if bid and ask:
                        self.callback(float(bid), float(ask), timestamp)
                    else:
                        self.logger.warning(f"Incomplete tick data: BID={bid} OFFER={ask}")

                except Exception as e:
                    self.logger.error(f"Error processing tick update: {e}", exc_info=True)

            def onSubscription(self):
                self.logger.info("✓ Subscription confirmed - waiting for ticks...")

            def onUnsubscription(self):
                self.logger.info("✗ Unsubscribed from tick stream")

            def onSubscriptionError(self, code, message):
                self.logger.error(f"✗ Subscription ERROR {code}: {message}")

        return TickListener(self.tick_callback, self.logger)

    def subscribe_positions(self, callback: Callable):
        """
        Subscribe to position updates (OPU, CONFIRMS, WOU).

        Args:
            callback: Function to call with position update data
        """
        self.position_callback = callback

        # Create subscription for TRADE data
        items = [f"TRADE:{self.account_id}"]
        fields = ["CONFIRMS", "OPU", "WOU"]

        self.trade_subscription = Subscription(
            mode="DISTINCT",
            items=items,
            fields=fields
        )

        # Set up listener
        self.trade_subscription.addListener(self._create_position_listener())

        # Subscribe
        self.client.subscribe(self.trade_subscription)
        self.logger.info(f"Subscribed to position updates for account {self.account_id}")

    def _create_position_listener(self):
        """Create position subscription listener."""

        class PositionListener:
            def __init__(self, callback, logger):
                self.callback = callback
                self.logger = logger

            def onItemUpdate(self, update):
                """Handle position update."""
                try:
                    # Get update type and data
                    confirms = update.getValue("CONFIRMS")
                    opu = update.getValue("OPU")
                    wou = update.getValue("WOU")

                    # Log the raw update
                    self.logger.debug(f"Position update: CONFIRMS={confirms}, OPU={opu}, WOU={wou}")

                    # Parse and forward to callback
                    if confirms:
                        self.logger.info(f"Deal confirmation received: {confirms}")
                        self.callback('CONFIRMS', confirms)

                    if opu:
                        self.logger.info(f"Position update (OPU): {opu}")
                        self.callback('OPU', opu)

                    if wou:
                        self.logger.info(f"Working order update (WOU): {wou}")
                        self.callback('WOU', wou)

                except Exception as e:
                    self.logger.error(f"Error processing position update: {e}", exc_info=True)

            def onSubscription(self):
                self.logger.info("✓ Position subscription confirmed - listening for updates...")

            def onUnsubscription(self):
                self.logger.info("✗ Unsubscribed from position updates")

            def onSubscriptionError(self, code, message):
                self.logger.error(f"✗ Position subscription ERROR {code}: {message}")

        return PositionListener(self.position_callback, self.logger)

    def connect(self):
        """Connect to Lightstreamer."""
        self.logger.info("Connecting to Lightstreamer...")
        self.client.connect()

    def disconnect(self):
        """Disconnect from Lightstreamer."""
        if self.market_subscription:
            self.client.unsubscribe(self.market_subscription)

        if self.trade_subscription:
            self.client.unsubscribe(self.trade_subscription)

        self.client.disconnect()
        self.logger.info("Disconnected from Lightstreamer")
