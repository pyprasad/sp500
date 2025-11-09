# Tick-Level Backtest Guide

## Overview

The tick-level backtest provides **realistic simulation** by processing every tick (10.7M ticks for 2024) instead of just 30-min bars. This catches intra-bar reversals and mirrors live trading behavior.

---

## Quick Start

### 1. Run Tick Backtest (Full Year 2024)

```bash
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_full_scaled.csv \
  --tp 40 \
  --market GERMANY40 \
  --out reports/tick_backtest_2024
```

**Expected runtime:** 3-8 minutes (processing 10.7M ticks)

### 2. Run Bar Backtest (for comparison)

```bash
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024 \
  --market GERMANY40 \
  --tp 40 \
  --out reports/bar_backtest_2024
```

**Expected runtime:** 5-10 seconds

### 3. Compare Results

```bash
python3 compare_bar_vs_tick.py \
  --bar-summary reports/bar_backtest_2024/summary_tp40.csv \
  --tick-summary reports/tick_backtest_2024/summary_tp40.csv \
  --output 2024_bar_vs_tick_comparison.txt
```

---

## What's Different?

| Feature | Bar Backtest | Tick Backtest |
|---------|--------------|---------------|
| **Data Points** | ~4,000 bars | ~10,700,000 ticks |
| **Update Frequency** | Every 30 min | Every tick |
| **Trailing Stop** | Updated on bar close | Updated on every tick |
| **SL/TP Check** | Bar high/low only | Every tick |
| **Exit Precision** | Bar-level approximation | Tick-level precision |
| **Runtime** | 5-10 seconds | 3-8 minutes |
| **Realism** | Approximate | High |

---

## Expected Results

### January 2024 Test Results:
- **Bar Backtest:** +75.38 pts (11 trades)
- **Tick Backtest:** +33.58 pts (11 trades)
- **Difference:** -41.80 pts (-55% worse)

**Why tick is lower:**
- Catches intra-bar reversals that hit trailing SL earlier
- More realistic exit timing
- Uses actual bid/ask prices from ticks

**Conclusion:** Tick backtest is more realistic. Bar backtest overestimates profit.

---

## Command Reference

### Full Year with Custom Settings

```bash
# Different TP
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_full_scaled.csv \
  --tp 50 \
  --market GERMANY40 \
  --out reports/tick_backtest_2024_tp50

# Debug mode
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_full_scaled.csv \
  --tp 40 \
  --market GERMANY40 \
  --out reports/tick_backtest_2024 \
  --log-level DEBUG
```

### Single Month Test (faster)

```bash
# Create single month file first
head -1 data/backtest/germany40_2024/dax_2024_full_scaled.csv > dax_jan_ticks.csv
awk -F',' '$2 ~ /^2024-01/ {print}' data/backtest/germany40_2024/dax_2024_full_scaled.csv >> dax_jan_ticks.csv

# Run backtest
python3 -m src.tick_backtest \
  --tick-data dax_jan_ticks.csv \
  --tp 40 \
  --market GERMANY40 \
  --out reports/tick_backtest_jan
```

---

## Output Files

Both backtests generate the same report files:

```
reports/tick_backtest_2024/
├── trades_tp40.csv      # Per-trade details
├── equity_tp40.csv      # Equity curve
└── summary_tp40.csv     # Aggregate metrics

reports/bar_backtest_2024/
├── trades_tp40.csv
├── equity_tp40.csv
└── summary_tp40.csv
```

---

## Troubleshooting

### Out of Memory
If tick backtest runs out of memory:
1. Process single months separately
2. Increase swap space
3. Use tick sampling (future enhancement)

### Slow Performance
Expected: ~1.5M ticks/minute
If slower:
1. Close other applications
2. Check disk I/O (use SSD)
3. Reduce log level to WARNING

### Different Trade Counts
If bar and tick have different number of trades:
- Check if entry signals align (they should)
- May indicate data quality issue
- Verify candle building is correct

---

## Key Insights from Tick Simulation

1. **Trailing Stop Performance**
   - Bar backtest may overestimate by 20-50%
   - Tick catches intra-bar reversals
   - More conservative/realistic

2. **Exit Timing**
   - Tick exits happen at exact moment SL hit
   - Bar exits approximate with bar.low/high
   - Tick is more accurate

3. **EOD Exits**
   - Tick uses last tick's bid price
   - Bar uses bar.close approximation
   - Small differences accumulate

4. **Confidence**
   - Use tick results for go-live decisions
   - Bar results useful for quick testing only

---

## Next Steps After Full Year Run

1. **Review Results**
   - Compare bar vs tick total P&L
   - Check trailing stop exit differences
   - Analyze win rate changes

2. **Validate Strategy**
   - If tick results still profitable → good to go live
   - If tick results break-even/negative → reconsider strategy

3. **Optimize Parameters**
   - Test different TP values (30, 40, 50)
   - Test trailing activation (20, 25, 30)
   - Test trailing distance (8, 10, 12)

---

## Support

If you encounter issues:
1. Check log files for errors
2. Verify tick data format matches expected
3. Ensure config.yaml has GERMANY40 market settings
4. Run January test first to validate setup
