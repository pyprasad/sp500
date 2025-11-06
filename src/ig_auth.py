"""IG API authentication and session management."""

import os
import requests
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv


class IGAuth:
    """Handles IG API authentication and token management."""

    def __init__(self):
        """Initialize IG authentication."""
        load_dotenv()

        self.api_key = os.getenv('IG_API_KEY')
        self.username = os.getenv('IG_USERNAME')
        self.password = os.getenv('IG_PASSWORD')
        self.account_type = os.getenv('IG_ACCOUNT_TYPE', 'DEMO')
        self.account_id = os.getenv('IG_ACCOUNT_ID')

        if not all([self.api_key, self.username, self.password]):
            raise ValueError("Missing IG credentials in environment variables")

        # Base URL for API
        self.base_url = 'https://demo-api.ig.com/gateway/deal' if self.account_type == 'DEMO' else 'https://api.ig.com/gateway/deal'

        # Session tokens
        self.cst_token: Optional[str] = None
        self.x_security_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.lightstreamer_endpoint: Optional[str] = None

        self.logger = logging.getLogger("rsi2_strategy.ig_auth")

    def authenticate(self) -> bool:
        """
        Authenticate with IG API and obtain session tokens.
        Tries Version 3 first (for Lightstreamer endpoint), falls back to Version 2.

        Returns:
            True if authentication successful
        """
        url = f"{self.base_url}/session"

        # Try Version 3 first (includes lightstreamerEndpoint)
        for version in ['3', '2']:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json; charset=UTF-8',
                'X-IG-API-KEY': self.api_key,
                'Version': version
            }

            payload = {
                'identifier': self.username,
                'password': self.password
            }

            try:
                self.logger.debug(f"Attempting authentication with Version {version}")
                response = requests.post(url, json=payload, headers=headers)

                # Log response status for debugging
                self.logger.debug(f"Authentication response status: {response.status_code}")

                response.raise_for_status()

                # Extract tokens from headers
                self.cst_token = response.headers.get('CST')
                self.x_security_token = response.headers.get('X-SECURITY-TOKEN')

                if not self.cst_token or not self.x_security_token:
                    self.logger.warning(f"Version {version} did not return tokens, trying next version...")
                    continue

                # Set token expiry (IG tokens typically last 6 hours)
                self.token_expiry = datetime.now() + timedelta(hours=6)

                # Get account info if account_id not set
                data = response.json()
                if not self.account_id and 'accountId' in data:
                    self.account_id = data['accountId']

                # Extract Lightstreamer endpoint (critical for streaming)
                if 'lightstreamerEndpoint' in data:
                    self.lightstreamer_endpoint = data['lightstreamerEndpoint']
                    self.logger.info(f"Lightstreamer endpoint: {self.lightstreamer_endpoint}")
                else:
                    self.logger.warning(f"No lightstreamerEndpoint in Version {version} response")

                self.logger.info(f"Successfully authenticated with IG API (Version {version})")
                return True

            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Authentication with Version {version} failed: {e}")
                if version == '2':
                    # Last attempt failed
                    self.logger.error(f"All authentication attempts failed")
                    return False
                # Try next version
                continue

        return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated with valid tokens."""
        if not self.cst_token or not self.x_security_token:
            return False

        if self.token_expiry and datetime.now() >= self.token_expiry:
            self.logger.warning("Authentication tokens expired")
            return False

        return True

    def ensure_authenticated(self) -> bool:
        """Ensure valid authentication, refreshing if needed."""
        if not self.is_authenticated():
            self.logger.info("Re-authenticating with IG API...")
            return self.authenticate()
        return True

    def get_headers(self) -> Dict[str, str]:
        """
        Get headers with authentication tokens for API requests.

        Returns:
            Dictionary of headers
        """
        if not self.is_authenticated():
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json; charset=UTF-8',
            'X-IG-API-KEY': self.api_key,
            'CST': self.cst_token,
            'X-SECURITY-TOKEN': self.x_security_token
        }

    def logout(self):
        """Logout and invalidate session tokens."""
        if not self.is_authenticated():
            return

        url = f"{self.base_url}/session"

        try:
            headers = self.get_headers()
            headers['Version'] = '1'
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            self.logger.info("Successfully logged out from IG API")

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Logout failed: {e}")

        finally:
            self.cst_token = None
            self.x_security_token = None
            self.token_expiry = None
            self.lightstreamer_endpoint = None
