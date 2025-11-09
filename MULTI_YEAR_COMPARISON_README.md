# Multi-Year Strategy Comparison

This script runs backtests across multiple years (2012, 2020-2024) and all three strategy modes (LONG, SHORT, BOTH) to produce a comprehensive P&L comparison table.

## Usage

Simply run the script:

```bash
python3 run_multi_year_comparison.py
```

## What It Does

1. **Runs 18 backtests total:**
   - 6 years × 3 modes = 18 tests
   - Each test uses tick-level data for realistic simulation

2. **Generates two output files:**
   - `reports/multi_year_comparison/simple_pnl_comparison.csv` - Easy-to-read P&L table
   - `reports/multi_year_comparison/detailed_comparison.csv` - Full metrics (trades, win rate, etc.)

3. **Prints summary table:**
   ```
   Year  LONG (pts)  SHORT (pts)  BOTH (pts)  LONG (£)      SHORT (£)     BOTH (£)
   2012  +123.45     -45.67       +78.90      £+246.90     £-91.34       £+157.80
   2020  +234.56     +123.45      +358.01     £+469.12     £+246.90      £+716.02
   ...
   ```

4. **Calculates totals** across all years

## Output Structure

```
reports/
└── multi_year_comparison/
    ├── simple_pnl_comparison.csv       # Simple P&L table
    ├── detailed_comparison.csv          # Full metrics
    ├── 2012_long/                       # Individual reports
    │   ├── trades_tp40.csv
    │   ├── equity_tp40.csv
    │   └── summary_tp40.csv
    ├── 2012_short/
    ├── 2012_both/
    ├── 2020_long/
    ... (18 directories total)
```

## Time Estimate

- **2012:** ~2-5 minutes (324MB tick data)
- **2020:** ~15-30 minutes (4.4GB tick data)
- **2021:** ~10-20 minutes (2.5GB tick data)
- **2022:** ~15-25 minutes (4.1GB tick data)
- **2023:** ~10-20 minutes (2.5GB tick data)
- **2024:** ~5-10 minutes (1.2GB tick data)

**Total estimated time:** 1-2 hours for all 18 backtests

## Features

✅ **Simple** - One command, no parameters needed
✅ **Safe** - Doesn't modify strategy code
✅ **Complete** - Tests all years and modes
✅ **Organized** - Saves all reports in separate folders
✅ **Summary** - Prints comparison table at the end

## Requirements

- Python 3.9+
- All dependencies installed (pandas, yaml)
- Tick data files in `data/backtest/germany40_*/dax_*_full_scaled.csv`

## Notes

- The script temporarily modifies `config.yaml` to change strategy mode, then restores it
- Each backtest runs with TP=40 pts (can be modified in script if needed)
- Uses GERMANY40 market configuration
- All backtests are independent - if one fails, others continue
