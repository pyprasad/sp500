# SHORT Strategy Implementation Status

## ✅ COMPLETED

### 1. Config Structure (config.yaml)
- ✅ Added `strategy_mode: "long"` (or "short" or "both")
- ✅ Added `starting_capital: 5000.0`
- ✅ Added `margin_requirement_pct: 5.0`
- ✅ Created `long:` section with all settings
- ✅ Created `short:` section with all settings
  - Overbought threshold: 96
  - TP: 40 pts, SL: 80 pts
  - Trailing: activation=25, distance=10
  - EOD: false (allow overnight)
- ✅ Kept legacy settings for backward compatibility

### 2. Margin Validator (src/margin_validator.py)
- ✅ Created `MarginValidator` class
- ✅ Margin calculation: `Price × Size × 5%`
- ✅ Balance tracking: Starting capital + Realized P&L only (Option B)
- ✅ Pre-trade validation: `can_open_position()`
- ✅ Blocks trades if insufficient margin (Option A)
- ✅ Tracks realized P&L on trade close

---

## 🔄 IN PROGRESS / TODO

### 3. Backtest Engine Updates (bt_engine.py)
- ⏳ Add SHORT entry logic (RSI ≥96, cross down)
- ⏳ Add SHORT exit logic (inverted TP/SL)
- ⏳ Add SHORT trailing stop (trails DOWN not UP)
- ⏳ Support 2 positions (1 LONG + 1 SHORT simultaneously)
- ⏳ Integrate margin validator
- ⏳ Add `trade_type` field to trades ("LONG" or "SHORT")
- ⏳ Track blocked trades (margin insufficient)

### 4. Tick Backtest Engine Updates (tick_backtest_engine.py)
- ⏳ Same as above for tick-level simulation

### 5. Reports Updates (bt_reports.py)
- ⏳ Add `trade_type` column to trades_tp40.csv
- ⏳ Show LONG vs SHORT breakdown in summary
- ⏳ Show margin-blocked trades count
- ⏳ Split metrics:
  - LONG: trades, P&L, win rate, etc.
  - SHORT: trades, P&L, win rate, etc.
  - COMBINED: totals

### 6. Comparison Script (compare_bar_vs_tick.py)
- ⏳ Update to show LONG/SHORT breakdown
- ⏳ Compare LONG performance (bar vs tick)
- ⏳ Compare SHORT performance (bar vs tick)

### 7. Testing
- ⏳ Test LONG-only (existing functionality - should not break)
- ⏳ Test SHORT-only (`strategy_mode: "short"`)
- ⏳ Test BOTH (`strategy_mode: "both"`)
- ⏳ Verify margin blocking works
- ⏳ Verify bar and tick backtests both work

---

## Implementation Notes

### SHORT Entry Logic (RSI Overbought Rebound)
```python
# Track overbought state
if rsi >= overbought_threshold:
    seen_overbought = True

# Enter SHORT when RSI crosses DOWN
if seen_overbought and rsi < overbought_threshold:
    enter_short_position()
    seen_overbought = False
```

### SHORT P&L Calculation
```python
# LONG: profit when price goes UP
long_pnl = exit_price - entry_price

# SHORT: profit when price goes DOWN
short_pnl = entry_price - exit_price
```

### SHORT Trailing Stop (Inverted)
```python
# LONG: SL trails UP behind price
# Entry: 16500, Price: 16600 → SL: 16590 (10 pts below)

# SHORT: SL trails DOWN above price
# Entry: 16500, Price: 16400 → SL: 16410 (10 pts above)

# Implementation
if trade_type == "SHORT":
    # Track LOWEST price (opposite of LONG)
    if current_bid < lowest_bid:
        lowest_bid = current_bid

    # SL = lowest + distance (above price)
    new_sl = lowest_bid + trailing_distance_pts
```

### Margin Blocking Example
```
Entry signal at 16,500
Required margin: 16,500 × 2.0 × 0.05 = £1,650
Current balance: £5,000
Already open: 1 LONG using £1,650
Free margin: £5,000 - £1,650 = £3,350
Can open? YES (£3,350 > £1,650)

Later...
Balance after losses: £3,000
Already open: 1 LONG using £1,650
Free margin: £3,000 - £1,650 = £1,350
New signal at 17,000 requires: £1,700
Can open? NO (£1,350 < £1,700)
→ Trade BLOCKED
```

---

## Testing Plan

### Test 1: LONG-Only (Verify No Breaking Changes)
```bash
# Should work exactly as before
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024/dax_2024-01.csv \
  --market GERMANY40 \
  --tp 40 \
  --out reports/test_long_only

# Verify: Same results as previous runs
```

### Test 2: SHORT-Only
```bash
# Update config: strategy_mode: "short"
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024/dax_2024-01.csv \
  --market GERMANY40 \
  --tp 40 \
  --out reports/test_short_only

# Check: Only SHORT trades in report
```

### Test 3: BOTH Strategies
```bash
# Update config: strategy_mode: "both"
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024/dax_2024-01.csv \
  --market GERMANY40 \
  --tp 40 \
  --out reports/test_both

# Check: Mix of LONG and SHORT trades
# Check: Max 2 positions open at once
```

### Test 4: Margin Blocking
```bash
# Update config: starting_capital: 2000.0 (very low)
python3 -m src.backtest \
  --data-path data/backtest/germany40_2024/dax_2024-01.csv \
  --market GERMANY40 \
  --tp 40 \
  --out reports/test_margin

# Check: Some trades blocked due to insufficient margin
```

### Test 5: Tick Backtest
```bash
# Same tests but with tick data
python3 -m src.tick_backtest \
  --tick-data data/backtest/germany40_2024/dax_2024_jan_ticks.csv \
  --market GERMANY40 \
  --tp 40 \
  --out reports/tick_test_short

# Verify: Works with SHORT strategy
```

---

## Next Steps

1. **Continue implementation** of bt_engine.py updates
2. **Test each mode** as implementation progresses
3. **Update documentation** (CLAUDE.md)
4. **Create usage examples** for SHORT strategy

---

## Configuration Examples

### LONG-Only (Current/Default)
```yaml
strategy_mode: "long"
starting_capital: 5000.0

long:
  enabled: true
  oversold_threshold: 5.0
  tp_pts: 40
  sl_pts: 100

short:
  enabled: false
```

### SHORT-Only (Test Overbought Strategy)
```yaml
strategy_mode: "short"
starting_capital: 5000.0

long:
  enabled: false

short:
  enabled: true
  overbought_threshold: 96.0
  tp_pts: 40
  sl_pts: 80
```

### BOTH (Maximum Opportunity)
```yaml
strategy_mode: "both"
starting_capital: 5000.0

long:
  enabled: true
  oversold_threshold: 5.0
  tp_pts: 40
  sl_pts: 100
  force_eod_exit: true

short:
  enabled: true
  overbought_threshold: 96.0
  tp_pts: 40
  sl_pts: 80
  force_eod_exit: false  # Can be different
```

---

## Files Modified/Created

### Created:
- `src/margin_validator.py` - Margin validation logic

### Modified (Completed):
- `config.yaml` - New structure with LONG/SHORT separation

### To Modify:
- `src/bt_engine.py` - Add SHORT logic
- `src/tick_backtest_engine.py` - Add SHORT logic
- `src/bt_reports.py` - Add LONG/SHORT breakdown
- `compare_bar_vs_tick.py` - Add LONG/SHORT comparison
- `CLAUDE.md` - Document SHORT strategy

---

**STATUS:** Configuration and margin validator complete. Ready to implement core SHORT strategy logic in backtest engines.
