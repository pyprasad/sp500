# Quick Start Guide

## Initial Setup (One-time)

```bash
# Run the setup script
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your IG Demo credentials.

## Backtesting

### Quick Test with Sample Data

```bash
# Test with sample CSV (included)
python -m src.backtest --data-path data/backtest/sample_us500_30m.csv --tp 5 --show-trades
```

### Full Backtest

```bash
# Place your historical CSVs in data/backtest/
# Then run:

# Test TP=5 pts
python -m src.backtest --data-path data/backtest --tp 5 --show-trades

# Test TP=10 pts
python -m src.backtest --data-path data/backtest --tp 10 --show-trades
```

### View Results

```bash
# Results saved to reports/backtest/
ls -lh reports/backtest/

# View trade details
cat reports/backtest/trades_tp5.csv

# View summary
cat reports/backtest/summary_tp5.csv
```

## Live Trading

### Dry Run (Recommended First)

Ensure `dry_run: true` in `config.yaml`, then:

```bash
# Test with TP=5 pts
python -m src.main --tp 5

# Test with TP=10 pts
python -m src.main --tp 10

# Stop with Ctrl+C
```

Dry run mode:
- ✓ Connects to IG and streams real data
- ✓ Builds candles and computes RSI
- ✓ Generates signals and logs trades
- ✗ Does NOT execute real orders

### Live Execution (Demo Account)

1. Set `dry_run: false` in `config.yaml`
2. Verify settings are correct
3. Run:

```bash
python -m src.main --tp 5
```

**Important**: Monitor actively. Stop with `Ctrl+C` for graceful shutdown.

## Checking Results

### Live Trading Logs

```bash
# View latest log
tail -f logs/runtime_*.log

# Trade history
cat data/trades/trades.csv
```

### Backtest Reports

```bash
# Summary metrics
cat reports/backtest/summary_tp5.csv

# All trades
cat reports/backtest/trades_tp5.csv

# Equity curve
cat reports/backtest/equity_tp5.csv
```

## Common Tasks

### Change Configuration

Edit `config.yaml`:

```yaml
stop_loss_pts: 2.0          # Adjust stop loss
spread_assumption_pts: 0.6  # Adjust spread
dry_run: true               # Toggle dry run
log_level: "DEBUG"          # Enable debug logs
```

### Test Different Parameters

```bash
# Custom stop loss and spread
python -m src.backtest \
  --data-path data/backtest \
  --tp 5 \
  --sl 3.0 \
  --spread 0.8

# Different session times
python -m src.backtest \
  --data-path data/backtest \
  --tp 10 \
  --open 09:00 \
  --close 16:30 \
  --skip-first 60
```

### Monitor Live Trading

```bash
# In one terminal - run the bot
python -m src.main --tp 5

# In another terminal - watch logs
tail -f logs/runtime_*.log

# Watch trades
tail -f data/trades/trades.csv
```

## Troubleshooting

### "Authentication failed"

- Check `.env` credentials
- Verify IG Demo account is active
- Ensure API key is correct

### "No CSV files found"

- Place CSVs in `data/backtest/`
- Verify CSV format (timestamp,open,high,low,close,volume)
- Check file has `.csv` extension

### "No trades executed" (backtest)

- Verify data covers US market hours (09:30-16:00 ET)
- Check RSI calculation (need at least 3-4 bars)
- Ensure prices create oversold rebound pattern
- Use `--show-trades` and check DEBUG logs

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Verify Python version
python --version  # Should be 3.11+
```

## File Locations

| Data Type | Location |
|-----------|----------|
| Configuration | `config.yaml` |
| Credentials | `.env` |
| Backtest CSVs | `data/backtest/*.csv` |
| Live ticks | `data/ticks/*.csv` |
| Live candles | `data/candles/*.csv` |
| Live trades | `data/trades/trades.csv` |
| Backtest results | `reports/backtest/*.csv` |
| Runtime logs | `logs/runtime_*.log` |

## Next Steps

1. **Understand the strategy**: Read README.md fully
2. **Test with sample data**: Run backtest on sample CSV
3. **Get historical data**: Obtain 30-min US 500 CSVs
4. **Backtest thoroughly**: Test both TP=5 and TP=10 configurations
5. **Dry run first**: Always test in dry run mode
6. **Monitor actively**: Never leave live trading unattended

## Getting Help

- Read the full README.md for detailed documentation
- Check CLAUDE.md for development guidelines
- Review source code comments for implementation details
- Test incrementally and verify each step
