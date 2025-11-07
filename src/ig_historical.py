"""Fetch historical price data from IG API."""

import logging
import requests
import csv
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from .ig_auth import IGAuth


class IGHistoricalData:
    """Handles fetching historical OHLC candle data from IG API."""

    def __init__(self, auth: IGAuth):
        """
        Initialize historical data fetcher.

        Args:
            auth: IGAuth instance for API authentication
        """
        self.auth = auth
        self.logger = logging.getLogger("rsi2_strategy.ig_historical")

    def fetch_historical_candles(
        self,
        epic: str,
        resolution: str,
        num_points: int = 50,
        market_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLC candles from IG API.

        Args:
            epic: Instrument EPIC code (e.g., IX.D.SPTRD.DAILY.IP)
            resolution: Candle resolution (MINUTE_30, HOUR, DAY, etc.)
            num_points: Number of historical candles to fetch (default 50)
            market_name: Market name for file naming (e.g., GERMANY40, US500)

        Returns:
            List of candle dictionaries with timestamp, open, high, low, close, volume
        """
        if not self.auth.ensure_authenticated():
            self.logger.error("Not authenticated, cannot fetch historical data")
            return []

        url = f"{self.auth.base_url}/prices/{epic}"
        headers = self.auth.get_headers()
        headers['Version'] = '3'

        # Request parameters
        params = {
            'resolution': resolution,
            'max': num_points,
            'pageSize': num_points  # Get all in one page
        }

        try:
            self.logger.info(f"Fetching {num_points} historical candles for {epic} ({resolution})...")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Check for price data
            if 'prices' not in data:
                self.logger.error(f"No price data in response: {data}")
                return []

            prices = data['prices']
            self.logger.info(f"Received {len(prices)} historical candles")

            # Convert IG format to internal candle format
            candles = self._convert_to_candles(prices)

            # Log data allowance info if available
            if 'metadata' in data and 'allowance' in data['metadata']:
                allowance = data['metadata']['allowance']
                self.logger.info(
                    f"Historical data allowance: {allowance.get('remainingAllowance', 'N/A')} / "
                    f"{allowance.get('totalAllowance', 'N/A')} remaining"
                )

            # Save candles to CSV for future reference
            if candles:
                self._save_to_csv(candles, epic, resolution, market_name)

            return candles

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch historical data: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                self.logger.error(f"Response: {e.response.text[:500]}")
            return []
        except Exception as e:
            self.logger.error(f"Error processing historical data: {e}", exc_info=True)
            return []

    def _convert_to_candles(self, prices: List[Dict]) -> List[Dict[str, Any]]:
        """
        Convert IG price data format to internal candle format.

        Args:
            prices: List of price records from IG API

        Returns:
            List of candle dictionaries
        """
        candles = []

        for price_record in prices:
            try:
                # Extract snapshot time (ISO format from IG)
                snapshot_time_str = price_record.get('snapshotTime', '')
                if not snapshot_time_str:
                    continue

                # Parse timestamp - IG returns in format like "2025-11-06T18:00:00"
                # or "2025/11/06 18:00:00" depending on version
                try:
                    if 'T' in snapshot_time_str:
                        timestamp = datetime.fromisoformat(snapshot_time_str.replace('Z', '+00:00'))
                    else:
                        # Handle format: "2025/11/06 18:00:00"
                        timestamp = datetime.strptime(snapshot_time_str, '%Y/%m/%d %H:%M:%S')
                        timestamp = pytz.UTC.localize(timestamp)
                except:
                    self.logger.warning(f"Could not parse timestamp: {snapshot_time_str}")
                    continue

                # Ensure timestamp is timezone-aware (UTC)
                if timestamp.tzinfo is None:
                    timestamp = pytz.UTC.localize(timestamp)

                # Extract OHLC data - use mid prices (average of bid/ask)
                # IG returns nested structure: {openPrice: {bid, ask}, closePrice: {bid, ask}, ...}
                open_price = self._extract_mid_price(price_record, 'openPrice')
                high_price = self._extract_mid_price(price_record, 'highPrice')
                low_price = self._extract_mid_price(price_record, 'lowPrice')
                close_price = self._extract_mid_price(price_record, 'closePrice')

                # Check if all prices are valid
                if None in [open_price, high_price, low_price, close_price]:
                    continue

                # Extract volume (may not always be present)
                last_traded_volume = price_record.get('lastTradedVolume', 0)

                candle = {
                    'timestamp': timestamp,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': last_traded_volume
                }

                candles.append(candle)

            except Exception as e:
                self.logger.warning(f"Error converting price record: {e}")
                continue

        # Sort by timestamp (oldest first)
        candles.sort(key=lambda x: x['timestamp'])

        return candles

    def _extract_mid_price(self, price_record: Dict, price_type: str) -> Optional[float]:
        """
        Extract mid price (average of bid and ask) from IG price structure.

        Args:
            price_record: Price record from IG API
            price_type: Type of price (openPrice, highPrice, lowPrice, closePrice)

        Returns:
            Mid price as float, or None if not available
        """
        try:
            price_data = price_record.get(price_type, {})

            # Try to get bid and ask
            bid = price_data.get('bid')
            ask = price_data.get('ask')

            if bid is not None and ask is not None:
                return (float(bid) + float(ask)) / 2.0

            # Fallback to lastTraded if bid/ask not available
            last_traded = price_data.get('lastTraded')
            if last_traded is not None:
                return float(last_traded)

            return None

        except (ValueError, TypeError) as e:
            self.logger.debug(f"Error extracting {price_type}: {e}")
            return None

    def get_resolution_from_timeframe(self, timeframe_sec: int) -> str:
        """
        Convert timeframe in seconds to IG resolution string.

        Args:
            timeframe_sec: Timeframe in seconds

        Returns:
            IG resolution string (e.g., 'MINUTE_30', 'HOUR', 'DAY')
        """
        # Map common timeframes to IG resolution strings
        resolution_map = {
            60: 'MINUTE',
            120: 'MINUTE_2',
            180: 'MINUTE_3',
            300: 'MINUTE_5',
            600: 'MINUTE_10',
            900: 'MINUTE_15',
            1800: 'MINUTE_30',
            3600: 'HOUR',
            7200: 'HOUR_2',
            10800: 'HOUR_3',
            14400: 'HOUR_4',
            86400: 'DAY',
            604800: 'WEEK',
            2592000: 'MONTH'
        }

        resolution = resolution_map.get(timeframe_sec)
        if not resolution:
            self.logger.warning(
                f"Unknown timeframe {timeframe_sec}s, defaulting to MINUTE_30"
            )
            return 'MINUTE_30'

        return resolution

    def _save_to_csv(self, candles: List[Dict[str, Any]], epic: str, resolution: str, market_name: str = None) -> None:
        """
        Save historical candles to CSV file for future reference.

        File naming: {market_name}_{resolution}.csv (reused on subsequent runs)
        If file exists, it will be overwritten with fresh data.

        Args:
            candles: List of candle dictionaries
            epic: Instrument EPIC code (for logging only)
            resolution: Candle resolution (e.g., MINUTE_30)
            market_name: Market name (e.g., GERMANY40, US500). If None, uses sanitized EPIC
        """
        try:
            # Create directory if it doesn't exist
            data_dir = Path('data/historical')
            data_dir.mkdir(parents=True, exist_ok=True)

            # Use market name if provided, otherwise sanitize epic
            if market_name:
                base_name = market_name
            else:
                base_name = epic.replace('.', '_').replace('IX_D_', '').replace('_DAILY_IP', '')

            # Clean filename format: MARKET_RESOLUTION.csv (no timestamp - reuse file)
            filename = f"{base_name}_{resolution}.csv"
            filepath = data_dir / filename

            # Write to CSV (overwrite if exists)
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                writer.writeheader()

                for candle in candles:
                    # Convert timestamp to ISO format string
                    row = {
                        'timestamp': candle['timestamp'].isoformat(),
                        'open': candle['open'],
                        'high': candle['high'],
                        'low': candle['low'],
                        'close': candle['close'],
                        'volume': candle['volume']
                    }
                    writer.writerow(row)

            self.logger.info(f"Saved {len(candles)} historical candles to {filepath}")

            # Log date range for verification
            if candles:
                first_date = candles[0]['timestamp'].strftime('%Y-%m-%d %H:%M')
                last_date = candles[-1]['timestamp'].strftime('%Y-%m-%d %H:%M')
                self.logger.info(f"Data range: {first_date} to {last_date}")

        except Exception as e:
            self.logger.warning(f"Failed to save historical candles to CSV: {e}")
