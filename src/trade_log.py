"""Trade logging to CSV and console."""

import csv
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


class TradeLogger:
    """Logs trades to CSV file and console."""

    def __init__(self, log_file: str = "data/trades/trades.csv"):
        """
        Initialize trade logger.

        Args:
            log_file: Path to trade log CSV file
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("rsi2_strategy.trade_log")

        # Initialize CSV file with headers if it doesn't exist
        if not self.log_file.exists():
            self._write_header()

    def _write_header(self):
        """Write CSV header."""
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'entry_time',
                'entry_price',
                'exit_time',
                'exit_price',
                'exit_reason',
                'tp_pts',
                'sl_pts',
                'pnl_pts',
                'pnl_gbp'
            ])

    def log_trade(self, trade: Dict[str, Any]):
        """
        Log trade to CSV and console.

        Args:
            trade: Trade dictionary
        """
        # Log to CSV
        with open(self.log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade['entry_time'].isoformat(),
                trade['entry_price'],
                trade['exit_time'].isoformat(),
                trade['exit_price'],
                trade['exit_reason'],
                trade['tp_pts'],
                trade['sl_pts'],
                trade['pnl_pts'],
                trade['pnl_gbp']
            ])

        # Log to console
        pnl_sign = '+' if trade['pnl_pts'] >= 0 else ''
        self.logger.info(
            f"TRADE CLOSED | "
            f"Entry: {trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S')} @ {trade['entry_price']:.2f} | "
            f"Exit: {trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S')} @ {trade['exit_price']:.2f} | "
            f"Reason: {trade['exit_reason']} | "
            f"P&L: {pnl_sign}{trade['pnl_pts']:.2f} pts / {pnl_sign}{trade['pnl_gbp']:.2f} GBP"
        )

    def get_trade_summary(self) -> Dict[str, Any]:
        """
        Get summary of all trades from log file.

        Returns:
            Dictionary with summary statistics
        """
        if not self.log_file.exists():
            return {
                'total_trades': 0,
                'total_pnl_pts': 0.0,
                'total_pnl_gbp': 0.0,
                'win_rate': 0.0
            }

        trades = []
        with open(self.log_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append({
                    'pnl_pts': float(row['pnl_pts']),
                    'pnl_gbp': float(row['pnl_gbp'])
                })

        if not trades:
            return {
                'total_trades': 0,
                'total_pnl_pts': 0.0,
                'total_pnl_gbp': 0.0,
                'win_rate': 0.0
            }

        total_trades = len(trades)
        total_pnl_pts = sum(t['pnl_pts'] for t in trades)
        total_pnl_gbp = sum(t['pnl_gbp'] for t in trades)
        winning_trades = sum(1 for t in trades if t['pnl_pts'] > 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            'total_trades': total_trades,
            'total_pnl_pts': total_pnl_pts,
            'total_pnl_gbp': total_pnl_gbp,
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades
        }

    def print_summary(self):
        """Print trade summary to console."""
        summary = self.get_trade_summary()

        self.logger.info("=" * 60)
        self.logger.info("TRADE SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total Trades:     {summary['total_trades']}")
        self.logger.info(f"Winning Trades:   {summary.get('winning_trades', 0)}")
        self.logger.info(f"Losing Trades:    {summary.get('losing_trades', 0)}")
        self.logger.info(f"Win Rate:         {summary['win_rate']:.2f}%")
        self.logger.info(f"Total P&L:        {summary['total_pnl_pts']:.2f} pts / "
                        f"{summary['total_pnl_gbp']:.2f} GBP")
        self.logger.info("=" * 60)
