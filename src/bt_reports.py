"""Backtest reporting and metrics generation."""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Any


class BacktestReporter:
    """Generate backtest reports and metrics."""

    def __init__(self, output_dir: str = "reports/backtest"):
        """
        Initialize reporter.

        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_reports(self, trades: List[Dict[str, Any]], tp_pts: float, sl_pts: float = None):
        """
        Generate all backtest reports.

        Args:
            trades: List of trade dictionaries
            tp_pts: Take profit value for naming files
            sl_pts: Stop loss value for display
        """
        if not trades:
            print(f"\n=== BACKTEST SUMMARY (TP={tp_pts} pts) ===")
            print("No trades executed.")
            return

        # Convert trades to DataFrame
        trades_df = pd.DataFrame(trades)

        # Save trades CSV
        trades_file = self.output_dir / f"trades_tp{int(tp_pts)}.csv"
        trades_df.to_csv(trades_file, index=False)
        print(f"Saved trades to {trades_file}")

        # Generate equity curve
        equity_df = self._generate_equity_curve(trades_df)
        equity_file = self.output_dir / f"equity_tp{int(tp_pts)}.csv"
        equity_df.to_csv(equity_file, index=False)
        print(f"Saved equity curve to {equity_file}")

        # Generate summary metrics
        summary = self._generate_summary(trades_df)

        # Add sl_pts to summary if provided
        if sl_pts is not None:
            summary['sl_pts'] = sl_pts

        summary_file = self.output_dir / f"summary_tp{int(tp_pts)}.csv"
        summary_df = pd.DataFrame([summary])
        summary_df.to_csv(summary_file, index=False)
        print(f"Saved summary to {summary_file}")

        # Print summary to console
        self._print_summary(summary, tp_pts)

        return summary

    def _generate_equity_curve(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Generate equity curve from trades."""
        equity_data = []
        equity_pts = 0.0
        equity_gbp = 0.0

        for _, trade in trades_df.iterrows():
            equity_pts += trade['pnl_pts']
            equity_gbp += trade['pnl_gbp']

            equity_data.append({
                'datetime': trade['datetime_close'],
                'equity_pts': equity_pts,
                'equity_gbp': equity_gbp
            })

        return pd.DataFrame(equity_data)

    def _generate_summary(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """Generate summary metrics."""
        total_trades = len(trades_df)

        # Count exits by reason
        tp_exits = len(trades_df[trades_df['exit_reason'] == 'TP'])
        sl_exits = len(trades_df[trades_df['exit_reason'] == 'SL'])
        eod_exits = len(trades_df[trades_df['exit_reason'] == 'EOD'])

        # Separate EOD exits into profitable and unprofitable
        eod_trades = trades_df[trades_df['exit_reason'] == 'EOD']
        eod_profitable = len(eod_trades[eod_trades['pnl_pts'] > 0])
        eod_breakeven = len(eod_trades[eod_trades['pnl_pts'] == 0])
        eod_losses = len(eod_trades[eod_trades['pnl_pts'] < 0])

        # Define wins/losses more accurately
        # TRUE WINS: Only TP exits (hit target)
        # LOSSES: SL exits + losing EOD exits
        # Note: Profitable EOD exits are not "wins" - they just didn't hit SL
        num_wins = tp_exits  # Only TP = true win
        num_losses = sl_exits + eod_losses  # SL + losing EOD = losses

        # For avg win/loss calculation, include all profitable/unprofitable trades
        winning_trades = trades_df[trades_df['pnl_pts'] > 0]
        losing_trades = trades_df[trades_df['pnl_pts'] < 0]

        win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0.0
        avg_win_pts = winning_trades['pnl_pts'].mean() if len(winning_trades) > 0 else 0.0
        avg_loss_pts = losing_trades['pnl_pts'].mean() if len(losing_trades) > 0 else 0.0

        payoff_ratio = abs(avg_win_pts / avg_loss_pts) if avg_loss_pts != 0 else 0.0
        expectancy_pts = trades_df['pnl_pts'].mean() if total_trades > 0 else 0.0

        total_pts = trades_df['pnl_pts'].sum()
        total_gbp = trades_df['pnl_gbp'].sum()

        # Calculate max drawdown
        equity_curve = trades_df['pnl_pts'].cumsum()
        running_max = equity_curve.expanding().max()
        drawdown = equity_curve - running_max
        max_drawdown_pts = drawdown.min()

        avg_bars_held = trades_df['bars_held'].mean()

        summary = {
            'trades': total_trades,
            'wins': num_wins,
            'losses': num_losses,
            'win_rate': round(win_rate, 2),
            'avg_win_pts': round(avg_win_pts, 3),
            'avg_loss_pts': round(avg_loss_pts, 3),
            'payoff_ratio': round(payoff_ratio, 3),
            'expectancy_pts': round(expectancy_pts, 3),
            'total_pts': round(total_pts, 2),
            'total_gbp': round(total_gbp, 2),
            'max_drawdown_pts': round(max_drawdown_pts, 2),
            'avg_bars_held': round(avg_bars_held, 1),
            'tp_exits': tp_exits,
            'sl_exits': sl_exits,
            'eod_exits': eod_exits,
            'eod_profitable': eod_profitable,
            'eod_losses': eod_losses
        }

        return summary

    def _print_summary(self, summary: Dict[str, Any], tp_pts: float):
        """Print formatted summary to console."""
        sl_display = f"{summary.get('sl_pts', 'N/A')}" if summary.get('sl_pts') else 'N/A'
        print(f"\n{'='*60}")
        print(f"BACKTEST SUMMARY (TP={tp_pts} pts, SL={sl_display} pts)")
        print(f"{'='*60}")
        print(f"Total Trades:        {summary['trades']}")
        print(f"Wins / Losses:       {summary['wins']} / {summary['losses']}")
        print(f"Win Rate:            {summary['win_rate']:.2f}%")
        print(f"Avg Win:             {summary['avg_win_pts']:.3f} pts")
        print(f"Avg Loss:            {summary['avg_loss_pts']:.3f} pts")
        print(f"Payoff Ratio:        {summary['payoff_ratio']:.3f}")
        print(f"Expectancy:          {summary['expectancy_pts']:.3f} pts")
        print(f"-" * 60)
        print(f"Total P&L:           {summary['total_pts']:.2f} pts / {summary['total_gbp']:.2f} GBP")
        print(f"Max Drawdown:        {summary['max_drawdown_pts']:.2f} pts")
        print(f"Avg Bars Held:       {summary['avg_bars_held']:.1f}")
        print(f"-" * 60)
        print(f"Exit Reasons:")
        print(f"  TP:                {summary['tp_exits']} (target hit)")
        print(f"  SL:                {summary['sl_exits']} (stop hit)")
        print(f"  EOD Total:         {summary['eod_exits']}")
        print(f"    EOD Profitable:  {summary.get('eod_profitable', 0)} (closed early with profit)")
        print(f"    EOD Losses:      {summary.get('eod_losses', 0)} (closed early at loss)")
        print(f"{'='*60}\n")

    def print_trades_detail(self, trades: List[Dict[str, Any]], max_trades: int = 50):
        """
        Print detailed trade information.

        Args:
            trades: List of trade dictionaries
            max_trades: Maximum number of trades to print
        """
        if not trades:
            print("No trades to display.")
            return

        print(f"\n{'='*100}")
        print(f"TRADE DETAILS (showing first {min(len(trades), max_trades)} of {len(trades)} trades)")
        print(f"{'='*100}")
        print(f"{'#':<4} {'Entry Time':<20} {'Entry':<8} {'Exit Time':<20} {'Exit':<8} {'Reason':<6} {'P&L Pts':<10} {'P&L GBP':<10} {'Bars':<5}")
        print(f"{'-'*100}")

        for i, trade in enumerate(trades[:max_trades], 1):
            print(f"{i:<4} "
                  f"{trade['ny_time_open']:<20} "
                  f"{trade['entry_price']:<8.2f} "
                  f"{trade['ny_time_close']:<20} "
                  f"{trade['exit_price']:<8.2f} "
                  f"{trade['exit_reason']:<6} "
                  f"{trade['pnl_pts']:>9.2f} "
                  f"{trade['pnl_gbp']:>9.2f} "
                  f"{trade['bars_held']:<5}")

        if len(trades) > max_trades:
            print(f"... and {len(trades) - max_trades} more trades")

        print(f"{'='*100}\n")
