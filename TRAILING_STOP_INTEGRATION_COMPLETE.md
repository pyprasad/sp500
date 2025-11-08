# Trailing Stop Integration - Complete

## Summary

Successfully integrated trailing stop functionality from backtest into live trading.

**Backtest Performance:**
- Fixed TP (40 pts): +731 pts (14.62% return)
- Trailing Stop (activation=25, distance=10): **+1,244 pts (24.89% return)** ✅
- **Improvement: +513 pts (+70% better!)**

---

## Implementation Complete

### Phase 1: Core Infrastructure ✅

1. **Broker Methods** ([src/broker.py](src/broker.py:164-206))
   - `update_stop_level(deal_id, new_sl)` - Updates SL via REST API
   - `get_position_by_deal_id(deal_id)` - Queries position for reconciliation
   - Both support dry_run mode

2. **Trailing Stop Manager** ([src/trailing_stop_manager.py](src/trailing_stop_manager.py))
   - Tracks highest bid reached
   - Activates at +25 pts profit
   - Maintains 10 pts distance behind highest
   - SL only moves UP, never down
   - Includes crash recovery via `restore_position()`

3. **IG Streaming Enhancement** ([src/ig_stream.py](src/ig_stream.py:138-208))
   - `subscribe_positions(callback)` - Listens to TRADE:{accountId}
   - Handles CONFIRMS, OPU, WOU messages
   - Instant notification of position closes

4. **Trade State Persistence** ([src/trade_state.py](src/trade_state.py))
   - Saves position on open (atomic write)
   - Clears position on close
   - NOT updated on every SL update (performance optimization)
   - Supports per-EPIC state files

### Phase 2: Main Integration ✅

5. **Main.py Updates** ([src/main.py](src/main.py))
   - Imports: TradeState, TrailingStopManager
   - Initialization in `__init__`:
     - TradeState with per-market file
     - TrailingStopManager (if enabled in config)
   - Startup reconciliation:
     - Load saved position
     - Verify with IG API
     - Restore trailing manager state
   - Main loop:
     - Process ticks through trailing manager
     - Update SL via REST API when triggered
   - Position opening:
     - Save trade state to JSON
     - Initialize trailing manager
   - Position closing:
     - Clear trade state
     - Reset trailing manager
   - Streaming integration:
     - Subscribe to position updates
     - Handle CONFIRMS (get deal_id)
     - Handle OPU (detect closes)

### Phase 3: Safety & Failsafes ✅

6. **Rate Limiting**
   - Minimum 2 seconds between SL updates
   - Prevents API spam
   - Debug log for skipped updates

7. **Error Recovery**
   - Reconciliation handles missing prices (falls back to entry price)
   - Reconciliation clears stale state if position doesn't exist
   - Position update parsing wrapped in try/except
   - Atomic file writes (temp file + rename)

---

## Configuration

### config.yaml Settings

```yaml
# Trailing stop configuration
use_trailing_stop: true
trailing_stop_distance_pts: 10
trailing_stop_activation_pts: 25

markets:
  GERMANY40:
    # ... existing settings ...
    state_file: "data/state/trade_state_GERMANY40.json"
```

---

## Testing Status

### Unit Tests ✅

1. **Broker Methods**
   - ✅ Syntax validated
   - ✅ Dry-run mode works

2. **Trailing Stop Manager**
   - ✅ Logic tested (activation, updates, no downward movement)
   - ✅ Tick sequence: 16720 (+20) → 16725 (+25, activate) → 16730 (+30, update) → 16728 (drop, no change)

3. **Trade State**
   - ✅ Save/load tested
   - ✅ Atomic write verified
   - ✅ Clear position tested
   - ✅ Handles missing file gracefully

4. **IG Streaming**
   - ✅ subscribe_positions() method exists
   - ✅ Listener handles CONFIRMS, OPU, WOU
   - ✅ Disconnect handles both subscriptions

5. **Main.py Integration**
   - ✅ Syntax validated
   - ✅ All imports work
   - ⏳ Live testing pending (requires IG credentials + market hours)

---

## Next Steps

### Recommended Testing Sequence

1. **Dry-Run Mode Testing** (No real orders)
   ```bash
   # Ensure dry_run: true in config.yaml
   python -m src.main --market GERMANY40 --tp 40
   ```

   **Expected Behavior:**
   - Connects to IG streaming
   - Receives ticks
   - Computes RSI
   - Logs [DRY RUN] position opens
   - Trailing stop manager activates at +25 pts
   - Logs [DRY RUN] SL updates
   - Position state saved to JSON

2. **State Persistence Testing**
   - Run in dry-run mode
   - Wait for position to open
   - Kill process (Ctrl+C)
   - Restart
   - **Expected:** Position restored, trailing continues

3. **Live Demo Testing** (with dry_run: false)
   - Start with small size (0.10 GBP/point)
   - Monitor logs for:
     - Position opening
     - Trailing activation at +25 pts
     - SL updates via API
     - Position closes (TP/SL/EOD)

---

## Key Design Decisions

1. **JSON Writes Minimized**
   - Only write on position open/close
   - NOT on every SL update (user's performance requirement)
   - Trailing state recalculated on restore

2. **Streaming + REST Hybrid**
   - Streaming: Listen for position updates (read-only)
   - REST API: Update SL levels (required, IG limitation)

3. **Rate Limiting**
   - 2-second minimum between SL updates
   - Prevents API throttling
   - Balances responsiveness vs. API limits

4. **Crash Recovery**
   - Reconcile on startup
   - Verify position exists on IG
   - Restore trailing from current price
   - Clear stale state automatically

5. **No Breaking Changes**
   - All existing functionality preserved
   - Trailing stop is optional (config flag)
   - Falls back gracefully if disabled

---

## Files Modified/Created

### New Files
- [src/trailing_stop_manager.py](src/trailing_stop_manager.py) (227 lines)
- [src/trade_state.py](src/trade_state.py) (128 lines)
- [test_trailing_stop_manager.py](test_trailing_stop_manager.py)
- [test_trade_state.py](test_trade_state.py)
- [test_position_subscription.py](test_position_subscription.py)

### Modified Files
- [src/broker.py](src/broker.py) (+106 lines) - Added update_stop_level, get_position_by_deal_id
- [src/ig_stream.py](src/ig_stream.py) (+77 lines) - Added subscribe_positions, position listener
- [src/main.py](src/main.py) (+128 lines) - Full trailing stop integration
- [config.yaml](config.yaml) - Added trailing stop settings + state_file

### No Changes
- src/strategy.py ✅
- src/risk.py ✅
- src/candle_builder.py ✅
- src/indicators.py ✅
- src/bt_engine.py ✅ (already has trailing stop)

---

## Benefits

1. **Performance:** +513 pts vs fixed TP (+70% improvement)
2. **Risk Management:** Locks in profits as position moves in favor
3. **Crash Recovery:** State persistence prevents loss of tracking
4. **Real-time Monitoring:** Streaming API for instant close notifications
5. **Scalable:** Per-market state files support multiple instruments
6. **Safe:** Rate limiting, error recovery, dry-run mode

---

## Validation Checklist

- ✅ All Python syntax valid
- ✅ Unit tests pass
- ✅ No breaking changes to existing code
- ✅ Configuration documented
- ✅ Logging comprehensive
- ✅ Error handling in place
- ✅ Rate limiting implemented
- ⏳ Live dry-run test pending
- ⏳ Live demo test pending

---

## Support & Troubleshooting

### Common Issues

1. **"Cannot update SL: no deal_id available"**
   - Wait for CONFIRMS message from streaming
   - Check streaming subscription is active

2. **"Saved position no longer exists on IG"**
   - Expected if position closed while bot was offline
   - State file automatically cleared

3. **"Skipping SL update (rate limited)"**
   - Normal behavior (prevents API spam)
   - SL updates max once per 2 seconds

4. **Trailing not activating**
   - Check profit reached activation_pts (default 25)
   - Check use_trailing_stop: true in config

### Logs to Monitor

- `logs/runtime_YYYYMMDD_HHMMSS.log` - Main trading log
- `data/state/trade_state_GERMANY40.json` - Current position (if open)
- `data/trades/trades_YYYYMMDD_HHMMSS.csv` - Completed trades

---

**Status:** Ready for dry-run testing
**Next:** User testing + feedback
