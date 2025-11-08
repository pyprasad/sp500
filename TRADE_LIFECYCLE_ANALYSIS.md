# Trade Management Lifecycle Analysis

## Current State Analysis

### 1. **Trade Lifecycle Overview**

```
SIGNAL → ENTRY → MONITORING → EXIT → LOGGING
```

#### Current Flow:
1. **Signal Generation** (strategy.py)
   - RSI calculation on completed 30-min candles
   - Oversold detection (RSI ≤ 5)
   - Entry signal when RSI crosses above 5

2. **Position Entry** (main.py → broker.py)
   - Get current bid/ask from tick stream
   - Calculate entry price (ask for long)
   - Calculate fixed TP/SL levels
   - **Submit market order to IG with fixed TP/SL**
   - Store position in memory (`current_position`)

3. **Position Monitoring** (main.py)
   - **PROBLEM**: No active monitoring after order placed!
   - IG manages TP/SL internally
   - No tick-by-tick tracking of position
   - No trailing stop updates

4. **Position Exit**
   - **Managed by IG API internally** (not by our code!)
   - TP/SL are set once at order creation
   - No dynamic updates possible

5. **Trade Logging** (trade_log.py)
   - Only logs AFTER trade closes
   - Writes to `data/trades/trades.csv`
   - No in-progress trade state persistence

---

## Critical Issues Identified

### ❌ **Issue #1: No Trade State Persistence**
**Problem:**
- Position details stored ONLY in memory (`self.current_position`)
- If process crashes/restarts, trade state is LOST
- No way to recover open positions

**Risk:**
- Position left open with no monitoring
- Can't resume trading after restart
- Data loss on system failure

---

### ❌ **Issue #2: No Trailing Stop Support in Live Trading**
**Problem:**
- TP/SL set once at order creation via `open_position()`
- IG API doesn't support dynamic TP/SL updates on existing positions
- Trailing stop logic exists in BACKTEST but NOT in LIVE

**Current broker.py:**
```python
def open_position(..., stop_level, limit_level):
    payload = {
        "stopLevel": stop_level,      # FIXED - can't update!
        "limitLevel": limit_level,     # FIXED - can't update!
    }
```

---

### ❌ **Issue #3: No Real-time Position Monitoring**
**Problem:**
- After order submitted, code waits for IG to hit TP/SL
- No tick-by-tick price tracking
- Can't implement dynamic exit logic (trailing stop)
- Can't track unrealized P&L

---

### ❌ **Issue #4: No Position Reconciliation**
**Problem:**
- No check if IG position matches our internal state
- If IG closes position (SL hit), we might not know immediately
- No periodic sync with IG positions API

---

## Solutions Required

### ✅ **Solution #1: Implement Trade State Persistence**

**Create:** `src/trade_state.py`

```python
class TradeState:
    """Persistent trade state management."""

    def __init__(self, state_file='data/state/trade_state.json'):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def save_position(self, position: dict):
        """Save active position to disk immediately."""
        state = {
            'position': position,
            'timestamp': datetime.now().isoformat(),
            'version': '1.0'
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def load_position(self) -> Optional[dict]:
        """Load position from disk on startup."""
        if not self.state_file.exists():
            return None
        with open(self.state_file, 'r') as f:
            state = json.load(f)
        return state.get('position')

    def clear_position(self):
        """Remove position state when closed."""
        if self.state_file.exists():
            self.state_file.unlink()
```

**Benefits:**
- Survives process restarts
- Can resume monitoring open positions
- Audit trail of all position changes

---

### ✅ **Solution #2: Implement Streaming-Based Trailing Stop**

**Problem:** IG API doesn't support updating TP/SL on open positions.

**Solution:** Manual position management via streaming + manual close

**Approach:**

1. **Don't use IG's TP/SL** - set very wide or omit
2. **Monitor position ourselves** via streaming ticks
3. **Manually close** when trailing stop hit

**Modified broker.py:**
```python
def open_position_manual_exit(self, direction: str, entry_price: float):
    """Open position WITHOUT TP/SL (we manage exits manually)."""
    payload = {
        "epic": self.epic,
        "direction": direction,
        "size": self.size,
        "orderType": "MARKET",
        "guaranteedStop": False,
        # NO stopLevel or limitLevel - we manage manually!
    }
    # Returns deal_id for later manual close
```

**New:** `src/trailing_stop_manager.py`
```python
class TrailingStopManager:
    """Manages trailing stop logic on streaming ticks."""

    def __init__(self, config):
        self.activation_pts = config.get('trailing_stop_activation_pts', 25)
        self.distance_pts = config.get('trailing_stop_distance_pts', 10)
        self.position = None
        self.highest_bid = None
        self.trailing_active = False
        self.trailing_sl_level = None

    def on_position_opened(self, entry_price, tp_level, sl_level):
        """Initialize tracking for new position."""
        self.position = {
            'entry_price': entry_price,
            'tp_level': tp_level,
            'sl_level': sl_level,
        }
        self.highest_bid = entry_price
        self.trailing_active = False
        self.trailing_sl_level = sl_level

    def on_tick(self, bid: float) -> tuple[bool, str]:
        """
        Process tick and check if exit needed.

        Returns:
            (should_exit, exit_reason)
        """
        if not self.position:
            return False, None

        # Update highest bid
        if bid > self.highest_bid:
            self.highest_bid = bid

        # Calculate current profit
        current_profit = bid - self.position['entry_price']

        # Activate trailing stop if threshold reached
        if not self.trailing_active and current_profit >= self.activation_pts:
            self.trailing_active = True
            logger.info(f"Trailing stop ACTIVATED at profit={current_profit:.2f}")

        # Update trailing SL if active
        if self.trailing_active:
            new_trailing_sl = self.highest_bid - self.distance_pts
            if new_trailing_sl > self.trailing_sl_level:
                self.trailing_sl_level = new_trailing_sl
                logger.debug(f"Trailing SL updated to {new_trailing_sl:.2f}")

        # Check exits
        # 1. Trailing SL (if active)
        if self.trailing_active and bid <= self.trailing_sl_level:
            return True, 'TRAILING_SL'

        # 2. Fixed SL (always active)
        if bid <= self.position['sl_level']:
            return True, 'SL'

        # 3. Fixed TP
        if bid >= self.position['tp_level']:
            return True, 'TP'

        return False, None
```

**Integration in main.py:**
```python
def on_tick(self, bid, ask, timestamp):
    """Handle tick with trailing stop monitoring."""
    self.current_bid = bid
    self.current_ask = ask

    # Build candles
    self.candle_builder.process_tick(bid, ask, timestamp)

    # Monitor open position (if any)
    if self.strategy.has_position():
        should_exit, exit_reason = self.trailing_stop_mgr.on_tick(bid)

        if should_exit:
            self.logger.info(f"Exit signal: {exit_reason} at bid={bid:.2f}")
            self._close_position_manual(bid, exit_reason)
```

---

### ✅ **Solution #3: Subscribe to Positions Stream**

**Reference:** https://labs.ig.com/streaming-api-reference

**Subscribe to:**
- `TRADE:{accountId}` - Trade confirmations
- Position updates in real-time

**Benefits:**
- Know immediately when IG closes position
- Get fill prices instantly
- Reconcile our state with IG

**Implementation:**
```python
# In ig_stream.py
def subscribe_to_positions(self, account_id):
    """Subscribe to position updates."""
    subscription = Subscription(
        mode="MERGE",
        items=[f"TRADE:{account_id}"],
        fields=["CONFIRMS", "OPU", "WOU"]
    )
    subscription.addlistener(self.on_position_update)
    self.client.subscribe(subscription)

def on_position_update(self, update):
    """Handle position update from stream."""
    # Update our internal state
    # Notify main trading loop
    pass
```

---

## Recommended Implementation Plan

### Phase 1: Add State Persistence (CRITICAL)
1. Create `src/trade_state.py`
2. Save position immediately after opening
3. Load position on startup
4. Clear on successful close

### Phase 2: Implement Streaming-Based Trailing Stop
1. Create `src/trailing_stop_manager.py`
2. Modify `broker.py` to open positions without TP/SL
3. Add tick-by-tick monitoring in `main.py`
4. Manually close via API when trailing stop hit

### Phase 3: Add Position Stream Subscription
1. Subscribe to IG positions stream
2. Reconcile our state with IG every tick
3. Handle unexpected closes

### Phase 4: Add Safety Mechanisms
1. Heartbeat monitoring (detect disconnects)
2. Position reconciliation on reconnect
3. Maximum position duration failsafe
4. Emergency close on critical errors

---

## Questions to Address

1. **Do we want manual exit management or trust IG's TP/SL?**
   - Manual = Trailing stop possible, more latency
   - IG managed = Lower latency, no trailing stop

2. **What happens if connection drops mid-trade?**
   - Need state persistence
   - Need reconnect logic
   - Need position recovery

3. **How to handle partial fills?**
   - IG might fill position in chunks
   - Need to track actual fill price vs intended

4. **Should we persist tick data?**
   - For audit trail
   - For debugging
   - For replay testing

---

## Next Steps

Let me know which solution you want to implement first:

A. **Trade State Persistence** (safest first step)
B. **Streaming-Based Trailing Stop** (most impactful for P&L)
C. **Position Stream Subscription** (best for robustness)
D. **All of the above** (comprehensive solution)
