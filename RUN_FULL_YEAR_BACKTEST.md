# Full Year 2024 Backtest - Quick Start

## Step 1: Run Bar Backtest (5-10 seconds)

```bash
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024 \
  --market GERMANY40 \
  --tp 40 \
  --out reports/bar_backtest_2024
```

## Step 2: Run Tick Backtest (3-8 minutes)

```bash
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_full_scaled.csv \
  --tp 40 \
  --market GERMANY40 \
  --out reports/tick_backtest_2024
```

**Expected:**
- Processing 10.7M ticks
- Building candles from ticks
- Running tick-level simulation
- ~3-8 minutes runtime

## Step 3: Compare Results

```bash
python3 compare_bar_vs_tick.py \
  --bar-summary reports/bar_backtest_2024/summary_tp40.csv \
  --tick-summary reports/tick_backtest_2024/summary_tp40.csv \
  --output 2024_bar_vs_tick_comparison.txt
```

Then view the comparison:

```bash
cat 2024_bar_vs_tick_comparison.txt
```

---

## All-in-One Command

Run all three steps sequentially:

```bash
# Step 1: Bar backtest
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024 \
  --market GERMANY40 \
  --tp 40 \
  --out reports/bar_backtest_2024

# Step 2: Tick backtest (THIS TAKES TIME)
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_full_scaled.csv \
  --tp 40 \
  --market GERMANY40 \
  --out reports/tick_backtest_2024

# Step 3: Compare
python3 compare_bar_vs_tick.py \
  --bar-summary reports/bar_backtest_2024/summary_tp40.csv \
  --tick-summary reports/tick_backtest_2024/summary_tp40.csv \
  --output 2024_bar_vs_tick_comparison.txt

# View results
cat 2024_bar_vs_tick_comparison.txt
```

---

## What to Expect

### Bar Backtest Output:
```
============================================================
BACKTEST SUMMARY (TP=40.0 pts, SL=100.0 pts)
============================================================
Total Trades:        XXX
Total P&L:           +XXX.XX pts / XXX.XX GBP
Win Rate:            XX.XX%
...
```

### Tick Backtest Output:
```
23:11:52 - rsi2_strategy.tick_backtest - INFO - Loaded 10,703,692 ticks from ...
23:11:52 - rsi2_strategy.tick_backtest - INFO - Built 4,XXX candles
...
Total Trades:        XXX
Total P&L:           +XXX.XX pts / XXX.XX GBP
```

### Comparison Output:
```
================================================================================
BACKTEST COMPARISON: BAR-ONLY vs TICK-LEVEL SIMULATION
================================================================================
Performance metrics side-by-side
Key findings
Recommendation for live trading
```

---

## After Completion

**Share with me:**
1. Final P&L from bar backtest: `XXX pts`
2. Final P&L from tick backtest: `XXX pts`
3. Difference: `XXX pts`
4. Number of trades: `XXX`

Or just paste the comparison file content!

---

## Troubleshooting

**If tick backtest takes too long (>15 min):**
- Normal for first run (Python compiling)
- Check CPU usage (should be 90-100% on one core)
- Let it complete - it's processing 10.7M ticks!

**If out of memory:**
- Close other applications
- Increase swap space
- Or run monthly backtests separately

**If errors:**
- Check the log output
- Verify tick data file exists and is readable
- Make sure config.yaml has GERMANY40 market settings
