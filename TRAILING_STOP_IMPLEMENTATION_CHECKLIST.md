# Trailing Stop Implementation Checklist

## Overview
Implement streaming-based trailing stop for live trading to match backtest performance (+1,244 pts vs +731 pts).

---

## Implementation Plan (Step-by-Step)

### ✅ **COMPLETED:**
- [x] Add trailing stop logic to backtest engine
- [x] Test and optimize trailing parameters (activation=25, distance=10)
- [x] Create trade state persistence module (`src/trade_state.py`)
- [x] Add state_file config to markets in config.yaml
- [x] Document complete flow in IMPLEMENTATION_PLAN.md

---

### 🔧 **TO-DO (In Order):**

#### **Phase 1: Core Infrastructure (No Breaking Changes)**

**1. Add Broker Methods for Position Management**
   - [ ] Add `update_stop_level(deal_id, new_sl)` to broker.py
   - [ ] Add `get_position_by_deal_id(deal_id)` to broker.py (for reconciliation)
   - [ ] Test both methods in isolation (dry run mode)
   - **Files:** `src/broker.py`
   - **Risk:** Low (new methods, existing code unchanged)

**2. Create Trailing Stop Manager**
   - [ ] Create `src/trailing_stop_manager.py`
   - [ ] Implement trailing logic (activation, distance, highest_bid tracking)
   - [ ] Add methods: `on_position_opened()`, `on_tick()`, `should_exit()`
   - [ ] Unit test trailing calculations
   - **Files:** `src/trailing_stop_manager.py` (NEW)
   - **Risk:** Low (new module, isolated)

**3. Enhance IG Streaming for Position Updates**
   - [ ] Add `subscribe_to_positions(account_id)` to ig_stream.py
   - [ ] Add callback handler for TRADE subscription
   - [ ] Parse OPU/CONFIRMS messages
   - [ ] Test subscription connection
   - **Files:** `src/ig_stream.py`
   - **Risk:** Medium (modifying existing streaming)

#### **Phase 2: Integration (Careful Changes)**

**4. Integrate Trade State Persistence**
   - [ ] Initialize TradeState in main.py with market-specific file
   - [ ] Save position state on open
   - [ ] Clear position state on close
   - [ ] Add startup recovery logic (load saved position)
   - **Files:** `src/main.py`
   - **Risk:** Medium (modifying main loop)

**5. Integrate Trailing Stop Manager**
   - [ ] Add config check for `use_trailing_stop` flag
   - [ ] Initialize TrailingStopManager if enabled
   - [ ] Call `on_tick()` in tick handler (only if position open)
   - [ ] Update SL via broker when trailing moves up
   - [ ] Add logging for trailing activations and updates
   - **Files:** `src/main.py`
   - **Risk:** Medium (modifying tick processing)

**6. Connect Streaming Position Updates**
   - [ ] Subscribe to TRADE stream on startup
   - [ ] Handle position close events from streaming
   - [ ] Map IG close reasons to our exit reasons (SL/TP/TRAILING_SL)
   - [ ] Trigger local close handler when streaming confirms close
   - **Files:** `src/main.py`, `src/ig_stream.py`
   - **Risk:** Medium (new event flow)

#### **Phase 3: Safety & Testing**

**7. Add Position Reconciliation**
   - [ ] On startup, check if saved position still exists on IG
   - [ ] If position closed offline, query IG for trade history
   - [ ] Clean up stale state files
   - [ ] Add periodic reconciliation (every 5 minutes)
   - **Files:** `src/main.py`
   - **Risk:** Low (safety feature)

**8. Add Failsafes**
   - [ ] Maximum position duration (force close after X hours)
   - [ ] Emergency close on critical errors
   - [ ] Heartbeat monitoring for streaming connection
   - [ ] Graceful shutdown (close positions cleanly)
   - **Files:** `src/main.py`
   - **Risk:** Low (safety features)

**9. Testing**
   - [ ] Test with trailing stop DISABLED (should work as before)
   - [ ] Test with trailing stop ENABLED on demo account
   - [ ] Test crash recovery (kill process, restart)
   - [ ] Test streaming disconnect/reconnect
   - [ ] Compare live results with backtest expectations
   - **Risk:** Low (validation)

**10. Documentation**
   - [ ] Update README with trailing stop usage
   - [ ] Document new config parameters
   - [ ] Add troubleshooting guide
   - [ ] Document state file format
   - **Risk:** None

---

## Configuration Changes Needed

### **config.yaml additions:**
```yaml
# Trailing stop configuration (already added)
use_trailing_stop: true
trailing_stop_distance_pts: 10
trailing_stop_activation_pts: 25

markets:
  GERMANY40:
    # ... existing config ...
    state_file: "data/state/trade_state_GERMANY40.json"  # Already added
```

---

## Files to Create/Modify

### **NEW Files:**
- `src/trailing_stop_manager.py` (trailing logic)

### **MODIFIED Files:**
- `src/broker.py` (add update_stop_level, get_position_by_deal_id)
- `src/ig_stream.py` (add position subscription)
- `src/main.py` (integrate all new components)

### **EXISTING Files (No Changes):**
- `src/strategy.py` (unchanged)
- `src/risk.py` (unchanged)
- `src/candle_builder.py` (unchanged)
- `src/indicators.py` (unchanged)

---

## Testing Strategy

### **1. Dry Run Testing (use_trailing_stop=false):**
```bash
python3 -m src.main --market GERMANY40
# Should work exactly as before (no breaking changes)
```

### **2. Dry Run Testing (use_trailing_stop=true):**
```bash
# Enable in config.yaml: use_trailing_stop: true
python3 -m src.main --market GERMANY40
# Should see trailing SL updates in logs (dry run mode)
```

### **3. Demo Account Testing:**
```bash
# Set dry_run: false in config.yaml
python3 -m src.main --market GERMANY40
# Real demo trades with trailing stop
```

### **4. Crash Recovery Testing:**
```bash
# Start trading, wait for position to open
python3 -m src.main --market GERMANY40

# Kill process (Ctrl+C or kill)
# Restart
python3 -m src.main --market GERMANY40
# Should resume monitoring saved position
```

---

## Risk Mitigation

### **For Each Change:**
1. ✅ Make change in isolated module first
2. ✅ Test in dry run mode
3. ✅ Test with trailing disabled (backward compatibility)
4. ✅ Test with trailing enabled
5. ✅ Commit working code before next change

### **Rollback Plan:**
- Keep git commits small (one feature per commit)
- Can revert to working state at any point
- Test suite validates no regressions

---

## Success Criteria

### **Functional:**
- [ ] Positions open with initial SL/TP
- [ ] Trailing SL updates sent to IG when price moves up
- [ ] Streaming receives close confirmations instantly
- [ ] Trade state persists and recovers on restart
- [ ] Backtest results match live trading behavior

### **Performance:**
- [ ] SL updates < 200ms latency
- [ ] Streaming notifications < 50ms latency
- [ ] No position state loss on crash
- [ ] Support multiple markets simultaneously

### **Safety:**
- [ ] No orphaned positions
- [ ] All closes logged to CSV
- [ ] State files cleaned up properly
- [ ] Graceful error handling

---

## Next Steps

**Ready to start Phase 1, Step 1:**
- Add `update_stop_level()` method to broker.py
- Add `get_position_by_deal_id()` method to broker.py

**Shall I proceed?**
