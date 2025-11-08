# Strategy Comparison Script - User Guide

## Overview

The `compare_strategies.py` script automatically compares **EOD Exit** vs **Overnight Holds** strategies by running both backtests and showing a clean side-by-side comparison.

**No code changes required!** The script temporarily modifies the config in memory only.

---

## Usage

### Basic Usage

```bash
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40
```

### With Custom Take Profit

```bash
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --tp 40
```

### Save Comparison to File

```bash
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --output report_2012.txt
```

### Different Market

```bash
python3 compare_strategies.py --data-path data/backtest/us500 --market US500 --tp 40
```

---

## Command-Line Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--data-path` | ✅ Yes | - | Path to historical data directory or CSV file |
| `--market` | ✅ Yes | - | Market to trade (e.g., GERMANY40, US500) |
| `--tp` | No | 40 | Take profit in points |
| `--config` | No | config.yaml | Path to config file |
| `--output` | No | None | Output file to save comparison report |

---

## What It Does

1. **Loads your config** from `config.yaml`
2. **Runs backtest #1:** With `force_eod_exit: true` (forces EOD exit)
3. **Runs backtest #2:** With `force_eod_exit: false` (allows overnight)
4. **Shows comparison:** Side-by-side metrics with differences highlighted
5. **Provides recommendation:** Which strategy is more profitable

---

## Output Format

```
====================================================================================================
STRATEGY COMPARISON: EOD EXIT vs OVERNIGHT HOLDS
====================================================================================================

Data Period: 2012-01-20 to 2012-12-21
Total Bars: 121 trades

====================================================================================================

Metric                                 EOD Exit (true)  Overnight (false)         Difference
----------------------------------------------------------------------------------------------------
PERFORMANCE
Total P&L (NET)                         +366.29 pts     +693.67 pts     +327.38 (+89%)
Return %                                     +7.33%         +13.87%             +6.54%
Final Balance                          £10,732.58       £11,387.34            +654.76

OVERNIGHT METRICS
Overnight Charges                          0.00 pts      +56.43 pts         +56.43 pts
Positions Held Overnight                  0 (0.0%)       54 (44.6%)                +54
Avg Days Held                                 0.00            0.71               0.71

RISK METRICS
Max Drawdown                            -370.91 pts     -476.86 pts        -105.95 pts

EXIT REASONS
Trailing SL Exits                       60 (+1667 pts)  97 (+3114 pts)             +37
EOD Exits                               55 (-701 pts)    0 (+0 pts)                -55

====================================================================================================

ANALYSIS:
----------------------------------------------------------------------------------------------------
✅ Overnight strategy is +89.4% MORE PROFITABLE (+327.38 pts)
   - Extra profit: +327.38 pts
   - Overnight charges: 56.43 pts
   - ROI on overnight costs: 5.8x (gained 5.8 pts for every 1 pt spent)
⚠️  Higher drawdown with overnight: -105.95 pts worse - ensure adequate capital

====================================================================================================
```

---

## Key Metrics Explained

### Performance Metrics
- **Total P&L (NET):** Final profit after all costs (including overnight charges)
- **Return %:** Percentage return on starting capital (£10,000)
- **Final Balance:** Ending account balance

### Overnight Metrics
- **Overnight Charges:** Total funding costs paid for holding overnight positions
- **Positions Held Overnight:** Number of trades that held past EOD
- **Avg Days Held:** Average number of days positions were held
- **Avg Bars Held:** Average number of 30-min bars held

### Risk Metrics
- **Max Drawdown:** Maximum peak-to-trough decline
- **Win Rate:** Percentage of winning trades

### Exit Reasons
- **Trailing SL Exits:** Number of exits via trailing stop (with total P&L)
- **SL Exits:** Number of exits via fixed stop loss
- **EOD Exits:** Number of forced EOD exits (only in force_eod_exit=true)

---

## Interpreting Results

### When Overnight is Better

If you see:
```
✅ Overnight strategy is +89% MORE PROFITABLE
   - ROI on overnight costs: 5.8x
```

**This means:**
- Allowing overnight holds is significantly more profitable
- The overnight charges are small relative to extra gains
- For every 1 pt spent on charges, you gained 5.8 pts in profit

**Consider using `force_eod_exit: false` in production**

### When EOD is Better

If you see:
```
❌ EOD strategy is 25% BETTER
   - Overnight charges hurt performance
```

**This means:**
- Forcing EOD exit performs better
- Overnight charges outweigh any potential gains
- Overnight gaps/volatility causing excessive SL hits

**Keep using `force_eod_exit: true` (current default)**

---

## Examples

### Test Multiple Years

```bash
# Compare 2012
python3 compare_strategies.py --data-path data/backtest/germany40_2012 --market GERMANY40 --output compare_2012.txt

# Compare 2013
python3 compare_strategies.py --data-path data/backtest/germany40_2013 --market GERMANY40 --output compare_2013.txt

# Compare 2014
python3 compare_strategies.py --data-path data/backtest/germany40_2014 --market GERMANY40 --output compare_2014.txt

# Review all reports
cat compare_*.txt | grep "ANALYSIS:" -A 5
```

### Test Different Markets

```bash
# DAX (Germany)
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --output dax_comparison.txt

# S&P 500 (US)
python3 compare_strategies.py --data-path data/backtest/us500 --market US500 --output sp500_comparison.txt
```

### Test Different TPs

```bash
# TP = 20
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --tp 20 --output compare_tp20.txt

# TP = 40
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --tp 40 --output compare_tp40.txt

# TP = 60
python3 compare_strategies.py --data-path data/backtest/germany40 --market GERMANY40 --tp 60 --output compare_tp60.txt
```

---

## Notes

- **No config changes:** Script modifies config in memory only, doesn't save changes
- **Original backtest untouched:** Uses existing backtest engine, no modifications
- **Fast:** Runs both tests in sequence (takes ~5 seconds for 5000 bars)
- **Clean output:** Easy to read, copy-paste friendly
- **File output optional:** Use `--output` to save for records

---

## Troubleshooting

### Error: "No trades generated"

**Cause:** Data path is empty or invalid

**Fix:** Check data path exists and contains CSV files

### Error: "Market not found in config"

**Cause:** Market name doesn't match config.yaml

**Fix:** Use exact market name from config (e.g., GERMANY40, not germany40)

### Different results than manual backtest

**Cause:** Config may have changed between runs

**Fix:** Script uses current config.yaml - ensure settings match your expectations

---

## Source Code

Located at: [compare_strategies.py](compare_strategies.py)

**Key features:**
- ~260 lines of clean Python code
- Uses existing backtest engine
- No external dependencies (uses built-in modules)
- Standalone script (doesn't modify any existing files)

---

**Happy testing!** 🚀

Use this script to quickly test different configurations and find the optimal strategy for your data.
