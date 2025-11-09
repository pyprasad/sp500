# SHORT Strategy Implementation Approach

## Problem
User set `strategy_mode: "short"` but backtest still runs LONG strategy because the code doesn't read the new config structure yet.

## Solution
Update `bt_engine.py` to:
1. Read new config structure (`long:` and `short:` sections)
2. Respect `strategy_mode` setting
3. Implement SHORT entry/exit logic
4. Support running BOTH strategies together

## Approach: Minimal Changes, Maximum Safety

### Step 1: Update `__init__` to Read New Config (Backward Compatible)

```python
def __init__(self, config: Dict[str, Any]):
    self.config = config
    self.session_clock = SessionClock(config)
    self.rsi_period = config.get('rsi_period', 2)

    # Strategy mode
    self.strategy_mode = config.get('strategy_mode', 'long')

    # Get LONG settings (with fallback to legacy)
    long_config = config.get('long', {})
    self.long_oversold = long_config.get('oversold_threshold', config.get('oversold', 5.0))
    self.long_tp = long_config.get('tp_pts', config.get('take_profits_pts', 40))
    self.long_sl = long_config.get('sl_pts', config.get('stop_loss_pts', 100))
    self.long_use_trailing = long_config.get('use_trailing_stop', config.get('use_trailing_stop', True))
    self.long_trailing_activation = long_config.get('trailing_activation_pts', config.get('trailing_stop_activation_pts', 25))
    self.long_trailing_distance = long_config.get('trailing_distance_pts', config.get('trailing_stop_distance_pts', 10))
    self.long_force_eod = long_config.get('force_eod_exit', config.get('force_eod_exit', True))

    # Get SHORT settings
    short_config = config.get('short', {})
    self.short_overbought = short_config.get('overbought_threshold', 96.0)
    self.short_tp = short_config.get('tp_pts', 40)
    self.short_sl = short_config.get('sl_pts', 80)
    self.short_use_trailing = short_config.get('use_trailing_stop', True)
    self.short_trailing_activation = short_config.get('trailing_activation_pts', 25)
    self.short_trailing_distance = short_config.get('trailing_distance_pts', 10)
    self.short_force_eod = short_config.get('force_eod_exit', False)

    # Margin validator
    from .margin_validator import MarginValidator
    self.margin_validator = MarginValidator(config)
```

###  Step 2: Update `run_backtest` to Support Multiple Positions

Current: Tracks 1 position
New: Track `long_position` and `short_position` separately

```python
def run_backtest(self, df: pd.DataFrame, tp_pts: float) -> List[Dict[str, Any]]:
    df = self.filter_session_bars(df)
    df['rsi'] = compute_rsi(df['close'], self.rsi_period)

    trades = []
    long_position = None   # Track LONG position
    short_position = None  # Track SHORT position

    # LONG state
    seen_oversold = False
    long_entry_signal = False

    # SHORT state
    seen_overbought = False
    short_entry_signal = False

    for idx, row in df.iterrows():
        # Check LONG entry logic (if mode is "long" or "both")
        if self.strategy_mode in ["long", "both"]:
            # ... existing LONG logic

        # Check SHORT entry logic (if mode is "short" or "both")
        if self.strategy_mode in ["short", "both"]:
            # NEW SHORT logic
            if row['rsi'] >= self.short_overbought:
                seen_overbought = True

            if seen_overbought and row['rsi'] < self.short_overbought:
                short_entry_signal = True
                seen_overbought = False

            # Execute SHORT entry
            if short_entry_signal and short_position is None:
                # Check margin
                open_positions = [p for p in [long_position, short_position] if p is not None]
                entry_price = row['open'] - (self.spread_pts / 2)  # BID for SHORT

                can_trade, reason = self.margin_validator.can_open_position(entry_price, open_positions)
                if can_trade:
                    short_position = {
                        'trade_type': 'SHORT',
                        'entry_price': entry_price,
                        # ... rest of position dict
                    }
                else:
                    # Log blocked trade
                    pass

        # Process exits for open positions
        # ... handle both long_position and short_position
```

### Step 3: SHORT Exit Logic (Inverted from LONG)

```python
# LONG exit logic (current)
bid_high = row['high'] - (spread / 2)
bid_low = row['low'] - (spread / 2)

if bid_low <= sl_level:  # SL hit
    exit_price = sl_level
elif bid_high >= tp_level:  # TP hit
    exit_price = tp_level

# SHORT exit logic (NEW - inverted)
ask_high = row['high'] + (spread / 2)  # Use ASK for SHORT exits
ask_low = row['low'] + (spread / 2)

if ask_high >= sl_level:  # SL hit (price went UP)
    exit_price = sl_level
elif ask_low <= tp_level:  # TP hit (price went DOWN)
    exit_price = tp_level

# SHORT P&L calculation
pnl_pts = entry_price - exit_price  # Inverted from LONG
```

### Step 4: SHORT Trailing Stop (Trails DOWN)

```python
# LONG trailing: track highest bid, SL below
if bid_high > position['highest_bid']:
    position['highest_bid'] = bid_high

if position['trailing_active']:
    new_sl = position['highest_bid'] - trailing_distance

# SHORT trailing: track LOWEST ask, SL above
if ask_low < position['lowest_ask']:
    position['lowest_ask'] = ask_low

if position['trailing_active']:
    new_sl = position['lowest_ask'] + trailing_distance
```

## Testing Strategy

1. **Test LONG-only (verify no breaking changes)**
   - Set `strategy_mode: "long"`
   - Run existing backtest
   - Results should match previous runs

2. **Test SHORT-only**
   - Set `strategy_mode: "short"`
   - Run backtest
   - Should only see SHORT trades

3. **Test BOTH**
   - Set `strategy_mode: "both"`
   - Run backtest
   - Should see mix of LONG and SHORT

4. **Test margin blocking**
   - Set `starting_capital: 2000`
   - Should see blocked trades

## Files to Modify

1. **src/bt_engine.py** - Core backtest logic
2. **src/bt_reports.py** - Add `trade_type` column, LONG/SHORT breakdown
3. **src/tick_backtest_engine.py** - Same changes for tick backtest

## Backward Compatibility

- If user doesn't have new config structure, falls back to legacy settings
- Default `strategy_mode: "long"` maintains current behavior
- Legacy settings still work (oversold, take_profits_pts, etc.)

## Implementation Order

1. ✅ Config structure (done)
2. ✅ Margin validator (done)
3. ⏳ Update bt_engine.__init__ to read new config
4. ⏳ Add SHORT entry logic
5. ⏳ Add SHORT exit logic
6. ⏳ Add SHORT trailing logic
7. ⏳ Add margin checks
8. ⏳ Add trade_type to reports
9. ⏳ Test each mode
10. ⏳ Repeat for tick_backtest_engine.py

---

**Next Action:** Implement Step 1 (update `__init__` to read new config with backward compatibility)
