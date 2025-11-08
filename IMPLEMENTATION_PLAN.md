# Trailing Stop Implementation Plan (Optimized)

## Summary of Optimizations

### ✅ Your Improvements:
1. **Minimize JSON writes** - Only on open/close, NOT on every SL update
2. **Use IG streaming for close events** - Listen for position updates instead of polling
3. **Per-market state files** - Configurable in config.yaml per EPIC

---

## Complete Flow

### 1. **Position Opens**

```python
def _open_position(self):
    # Get current prices
    entry_price = ask

    # Calculate initial levels
    initial_sl = entry_price - 100
    fixed_tp = entry_price + 40

    # Open via IG API
    deal_id = broker.open_position(
        direction='BUY',
        stop_level=initial_sl,   # Will be updated via streaming
        limit_level=fixed_tp     # Fixed
    )

    # Create position state
    position = {
        'deal_id': deal_id,
        'entry_price': entry_price,
        'entry_time': datetime.now().isoformat(),
        'tp_level': fixed_tp,
        'sl_level': initial_sl,
        'highest_bid': entry_price,
        'trailing_active': False,
        'status': 'OPEN'
    }

    # ✅ SAVE TO JSON (once!)
    self.trade_state.save_position(position)

    # Store in memory
    self.current_position = position
```

---

### 2. **Streaming Ticks (Every Tick)**

```python
def on_tick(self, bid: float, ask: float, timestamp: str):
    """Handle incoming tick from Lightstreamer."""

    # Update current prices
    self.current_bid = bid
    self.current_ask = ask

    # Build candles
    self.candle_builder.process_tick(bid, ask, timestamp)

    # ✅ MONITOR POSITION (if open)
    if self.current_position:
        self._update_trailing_stop(bid)
```

---

### 3. **Trailing Stop Updates (Memory Only)**

```python
def _update_trailing_stop(self, bid: float):
    """
    Update trailing stop based on current bid.

    ❌ Does NOT write to JSON (too frequent!)
    ✅ Only updates IG via API
    """
    pos = self.current_position

    # Update highest bid
    if bid > pos['highest_bid']:
        pos['highest_bid'] = bid

    # Calculate profit
    current_profit = bid - pos['entry_price']

    # Activate trailing if threshold reached
    if not pos['trailing_active'] and current_profit >= 25:
        pos['trailing_active'] = True
        self.logger.info(f"Trailing stop ACTIVATED at profit={current_profit:.2f}")

    # Calculate new SL if trailing active
    if pos['trailing_active']:
        new_sl = pos['highest_bid'] - 10

        # Only move SL UP (never down)
        if new_sl > pos['sl_level']:
            # ✅ UPDATE VIA IG API (fast!)
            success = self.broker.update_stop_level(
                deal_id=pos['deal_id'],
                new_stop_level=new_sl
            )

            if success:
                # Update in-memory state
                pos['sl_level'] = new_sl

                # ❌ NO JSON WRITE HERE!
                # (If crash, we recalculate from current price)

                self.logger.debug(f"Trailing SL updated to {new_sl:.2f}")
```

---

### 4. **Position Closes (via IG Streaming Event)**

```python
def on_position_update(self, update: dict):
    """
    Handle position update from IG streaming.

    ✅ IG tells us when position closes!
    ✅ No polling needed!

    Streaming message format:
    {
        "dealId": "DEAL123",
        "status": "CLOSED",
        "level": 16720.5,  # Exit price
        "reason": "STOP_LOSS" or "TAKE_PROFIT",
        "profit": 20.5
    }
    """
    if update.get('status') == 'CLOSED':
        deal_id = update.get('dealId')

        # Check if this is our current position
        if self.current_position and self.current_position['deal_id'] == deal_id:

            exit_price = update.get('level')
            ig_reason = update.get('reason')

            # Map IG reason to our exit reason
            if ig_reason == 'STOP_LOSS':
                # Was it trailing SL or original SL?
                exit_reason = 'TRAILING_SL' if self.current_position['trailing_active'] else 'SL'
            elif ig_reason == 'TAKE_PROFIT':
                exit_reason = 'TP'
            else:
                exit_reason = 'UNKNOWN'

            # Close position locally
            self._on_position_closed(exit_price, exit_reason)
```

---

### 5. **Local Position Close Handler**

```python
def _on_position_closed(self, exit_price: float, exit_reason: str):
    """
    Handle position close event.

    Called when:
    - IG streaming sends close confirmation
    - Manual close requested
    - EOD forced close
    """
    if not self.current_position:
        self.logger.warning("No position to close")
        return

    # Calculate P&L
    entry_price = self.current_position['entry_price']
    pnl_pts = exit_price - entry_price
    pnl_gbp = pnl_pts * self.config['size_gbp_per_point']

    # Create trade record
    trade = {
        'entry_time': datetime.fromisoformat(self.current_position['entry_time']),
        'entry_price': entry_price,
        'exit_time': datetime.now(),
        'exit_price': exit_price,
        'exit_reason': exit_reason,
        'tp_pts': self.tp_pts,
        'sl_pts': self.config['stop_loss_pts'],
        'pnl_pts': pnl_pts,
        'pnl_gbp': pnl_gbp
    }

    # Log trade to CSV
    self.trade_logger.log_trade(trade)

    # ✅ DELETE STATE FILE (position closed)
    self.trade_state.clear_position()

    # Clear in-memory state
    self.current_position = None
    self.current_deal_ref = None

    self.logger.info(f"Position closed: {exit_reason}, P&L: {pnl_pts:+.2f} pts")
```

---

### 6. **Startup Recovery**

```python
def start(self):
    """Start live trading with crash recovery."""

    # Initialize state manager (per-market file from config)
    state_file = self.config.get('state_file', 'data/state/trade_state.json')
    self.trade_state = TradeState(state_file)

    # Connect to IG
    self.auth.login()

    # ✅ CHECK FOR SAVED POSITION
    saved_position = self.trade_state.load_position()

    if saved_position:
        # Verify position still exists on IG
        deal_id = saved_position['deal_id']
        ig_position = self.broker.get_position_by_deal_id(deal_id)

        if ig_position:
            # ✅ Position still open - resume monitoring
            self.current_position = saved_position
            self.current_deal_ref = deal_id

            self.logger.warning("RESUMING monitoring of saved position")

            # Re-subscribe to streaming
            self.stream.subscribe_market(self.config['epic'])
            self.stream.subscribe_positions(self.account_id)

        else:
            # ❌ Position closed while offline
            self.logger.warning("Saved position no longer exists on IG")
            self.logger.warning("Position was closed while process was offline")

            # Clear stale state
            self.trade_state.clear_position()

            # TODO: Query IG for recent closed trades to get exit details

    # Continue normal operation
    self.logger.info("Live trading started")
```

---

## JSON File Strategy

### Per-Market Files (Configured in config.yaml):

```yaml
markets:
  GERMANY40:
    state_file: "data/state/trade_state_GERMANY40.json"

  US500:
    state_file: "data/state/trade_state_US500.json"
```

### File Lifecycle:

| Event | JSON Action | Reason |
|---|---|---|
| Position opens | **WRITE** | Save initial state for crash recovery |
| Trailing SL updates | **NONE** | Too frequent, not critical |
| Position closes (TP/SL) | **DELETE** | Position no longer exists |
| Process starts | **READ** | Recover from crash |
| Reconciliation (position gone) | **DELETE** | Clean up stale state |

---

## Benefits of This Approach

### 1. **Minimal Disk I/O** ✅
- JSON writes: ~2-3 per trade (open + close)
- NOT on every tick (could be 100+ writes per trade!)
- Fast, efficient

### 2. **Crash Recovery** ✅
- Can resume monitoring after restart
- Position details preserved
- Recalculate trailing from current price

### 3. **Low Latency** ✅
- IG streaming for close events (~10-50ms)
- Update SL via API (~50-200ms)
- No unnecessary polling

### 4. **Reliable** ✅
- IG manages final exit (SL on their server)
- Survives disconnects
- Streaming tells us immediately when closed

### 5. **Multi-Market Support** ✅
- Separate state file per EPIC
- Can run multiple markets simultaneously
- No state collision

---

## Next Steps

1. ✅ Create `trade_state.py` (DONE)
2. Add `update_stop_level()` to `broker.py`
3. Subscribe to IG position stream in `ig_stream.py`
4. Integrate trailing stop manager in `main.py`
5. Add startup recovery logic
6. Test on demo account

Ready to implement the broker API updates?
