"""Utility functions for configuration and logging."""

import logging
import yaml
from pathlib import Path
from typing import Any, Dict
from datetime import datetime
import pytz


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_market_config(config: Dict[str, Any], market_name: str = None) -> Dict[str, Any]:
    """
    Get configuration for a specific market.

    Merges global config with market-specific settings.
    Market-specific settings override global ones.

    Args:
        config: Full configuration dictionary
        market_name: Name of market (e.g., 'US500', 'GERMANY40').
                    If None, uses default_market from config.

    Returns:
        Merged configuration dictionary

    Raises:
        ValueError: If market not found in config
    """
    # Get market name
    if market_name is None:
        market_name = config.get('default_market', 'US500')

    # Check if markets section exists
    if 'markets' not in config:
        # Legacy config without markets section - return as is
        return config

    # Check if market exists
    if market_name not in config['markets']:
        available = list(config['markets'].keys())
        raise ValueError(f"Market '{market_name}' not found. Available markets: {available}")

    # Start with global config (exclude markets section)
    merged = {k: v for k, v in config.items() if k != 'markets'}

    # Merge market-specific settings (they override global)
    market_config = config['markets'][market_name]
    merged.update(market_config)

    return merged


def list_available_markets(config: Dict[str, Any]) -> list:
    """
    List all available markets in config.

    Args:
        config: Configuration dictionary

    Returns:
        List of market names
    """
    if 'markets' not in config:
        return []
    return list(config['markets'].keys())


def setup_logging(log_level: str = "INFO", log_file: str = None) -> logging.Logger:
    """Configure logging for the application."""
    logger = logging.getLogger("rsi2_strategy")
    logger.setLevel(getattr(logging, log_level.upper()))

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def parse_time(time_str: str) -> tuple[int, int]:
    """Parse time string 'HH:MM' to (hour, minute) tuple."""
    hour, minute = map(int, time_str.split(':'))
    return hour, minute


def get_ny_time(dt: datetime = None) -> datetime:
    """Convert datetime to America/New_York timezone."""
    tz = pytz.timezone('America/New_York')
    if dt is None:
        return datetime.now(tz)
    if dt.tzinfo is None:
        # Assume UTC if no timezone
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(tz)


def ensure_dir(path: str):
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)
