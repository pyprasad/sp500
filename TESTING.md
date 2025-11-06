# Testing Checklist

## Pre-Testing Setup

- [ ] Python 3.11+ installed
- [ ] Virtual environment created (`python3 -m venv venv`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with IG Demo credentials
- [ ] `config.yaml` reviewed and understood

## Backtest Testing

### Basic Functionality

- [ ] **Test with sample data**
  ```bash
  python -m src.backtest --data-path data/backtest/sample_us500_30m.csv --tp 5 --show-trades
  ```
  - [ ] Script runs without errors
  - [ ] Loads CSV successfully
  - [ ] Shows bar count and date range
  - [ ] Displays trades (if any signals present)
  - [ ] Generates report files in `reports/backtest/`

- [ ] **Test TP=10 variant**
  ```bash
  python -m src.backtest --data-path data/backtest/sample_us500_30m.csv --tp 10 --show-trades
  ```
  - [ ] Runs successfully
  - [ ] Creates separate report files (tp10)

### With Real Historical Data

- [ ] Obtain US 500 30-minute historical data
- [ ] Place CSV files in `data/backtest/`
- [ ] Verify CSV format matches requirements

- [ ] **Run full backtest TP=5**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 5 --show-trades
  ```
  - [ ] Processes all CSV files
  - [ ] Sorts by timestamp correctly
  - [ ] Filters to US session hours
  - [ ] Computes RSI(2) correctly
  - [ ] Detects oversold rebound signals
  - [ ] Applies entry window (10:00 ET onwards)
  - [ ] Models spread correctly (ask entry, bid exits)
  - [ ] Handles same-bar TP/SL (SL first)
  - [ ] Forces EOD exit
  - [ ] Generates complete reports

- [ ] **Run full backtest TP=10**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 10 --show-trades
  ```
  - [ ] Different results from TP=5 (higher TP)
  - [ ] Creates separate report files

### Verify Backtest Reports

- [ ] **trades_tp5.csv**
  - [ ] Contains all expected columns
  - [ ] Entry/exit times in correct timezone
  - [ ] Prices are reasonable
  - [ ] P&L calculations correct
  - [ ] Exit reasons make sense (TP/SL/EOD)

- [ ] **equity_tp5.csv**
  - [ ] Cumulative equity matches trade P&L
  - [ ] Timestamps match trade close times

- [ ] **summary_tp5.csv**
  - [ ] Win rate calculated correctly
  - [ ] Total P&L matches sum of trades
  - [ ] Metrics are reasonable

### Edge Cases

- [ ] Empty directory (should handle gracefully)
- [ ] CSV with no session data (should report no trades)
- [ ] CSV with missing columns (should error clearly)
- [ ] Single file vs directory (both work)

## Live Trading Testing

### Dry Run Mode (REQUIRED FIRST)

- [ ] Verify `dry_run: true` in `config.yaml`
- [ ] IG Demo credentials in `.env`

- [ ] **Start dry run**
  ```bash
  python -m src.main --tp 5
  ```
  - [ ] Authenticates with IG successfully
  - [ ] Connects to Lightstreamer
  - [ ] Receives tick data
  - [ ] Logs ticks to CSV (`data/ticks/`)
  - [ ] Builds 30-minute candles
  - [ ] Saves candles to CSV (`data/candles/`)
  - [ ] Computes RSI(2) on completed bars
  - [ ] Displays current RSI values
  - [ ] Detects new trading days
  - [ ] Resets daily state appropriately

- [ ] **Wait for signal**
  - [ ] Monitors for oversold condition (RSI ≤ 3.0)
  - [ ] Detects rebound (RSI > 3.0)
  - [ ] Checks session timing (10:00-15:59 ET)
  - [ ] Generates entry signal
  - [ ] Logs "[DRY RUN] Would open BUY position"
  - [ ] Does NOT execute real order

- [ ] **Monitor position (if opened)**
  - [ ] Tracks position state
  - [ ] Checks TP/SL levels
  - [ ] Detects exit conditions
  - [ ] Logs trade to `data/trades/trades.csv`
  - [ ] Shows P&L calculation

- [ ] **EOD behavior**
  - [ ] Detects end of session
  - [ ] Forces position flat if open
  - [ ] Logs EOD exit

- [ ] **Graceful shutdown**
  - [ ] Press `Ctrl+C`
  - [ ] Closes open position (if any)
  - [ ] Completes current candle
  - [ ] Stops tick logging
  - [ ] Disconnects from Lightstreamer
  - [ ] Prints session summary
  - [ ] Exits cleanly

### Verify Dry Run Data

- [ ] **Tick data** (`data/ticks/ticks_*.csv`)
  - [ ] Contains timestamp, bid, ask, mid
  - [ ] Timestamps are sequential
  - [ ] Prices are reasonable

- [ ] **Candle data** (`data/candles/candles_*.csv`)
  - [ ] Contains OHLCV columns
  - [ ] 30-minute intervals
  - [ ] OHLC relationships valid (L≤O,C≤H)

- [ ] **Trade log** (`data/trades/trades.csv`)
  - [ ] Entry/exit times recorded
  - [ ] Prices match expected levels
  - [ ] P&L calculated correctly

- [ ] **Runtime logs** (`logs/runtime_*.log`)
  - [ ] No error messages (or only expected warnings)
  - [ ] Clear event sequence
  - [ ] Signal generation visible

### Live Execution (Optional, Demo Only)

⚠️ **WARNING**: Only proceed if you fully understand the system and risks.

- [ ] Reviewed all code thoroughly
- [ ] Understand the strategy completely
- [ ] Verified dry run behavior multiple times
- [ ] Set `dry_run: false` in `config.yaml`
- [ ] Prepared to monitor actively

- [ ] **Run live on Demo**
  ```bash
  python -m src.main --tp 5
  ```
  - [ ] Authenticates successfully
  - [ ] Receives tick data
  - [ ] Builds candles correctly
  - [ ] Generates signals as expected
  - [ ] **Executes real orders** (BUY market)
  - [ ] Sets TP/SL levels on orders
  - [ ] Monitors position actively
  - [ ] Exits at TP, SL, or EOD
  - [ ] Records trade results

- [ ] **Verify in IG Platform**
  - [ ] Log into IG Demo web/app
  - [ ] Check positions match system state
  - [ ] Verify orders executed correctly
  - [ ] Confirm TP/SL levels set

## Configuration Testing

### Parameter Variations

- [ ] **Different stop loss**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 5 --sl 3.0
  ```

- [ ] **Different spread**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 5 --spread 0.8
  ```

- [ ] **Different session times**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 5 --open 09:00 --close 16:30
  ```

- [ ] **Skip more minutes**
  ```bash
  python -m src.backtest --data-path data/backtest --tp 5 --skip-first 60
  ```

## Validation Checks

### Strategy Logic

- [ ] RSI calculation matches manual calculation
- [ ] Oversold detection works (RSI ≤ 3.0)
- [ ] Rebound trigger works (RSI crosses above 3.0)
- [ ] Entry only after seeing oversold
- [ ] Entry window enforced (10:00 ET onwards)
- [ ] Single position limit enforced
- [ ] TP exit at correct level
- [ ] SL exit at correct level
- [ ] EOD exit before 16:00 ET
- [ ] Same-bar SL priority works

### Timing & Session

- [ ] Timestamp conversion to ET correct
- [ ] Session filtering works (09:30-16:00 ET)
- [ ] Entry window filtering works (10:00+ ET)
- [ ] Daily state reset at new trading day
- [ ] EOD detection accurate

### Spread Modeling

- [ ] Entry at ask (open + spread/2 in backtest)
- [ ] TP check uses bid (high ≥ entry + TP)
- [ ] SL check uses bid (low ≤ entry - SL)
- [ ] EOD exit at bid (close - spread/2)

### Reporting

- [ ] All trades recorded
- [ ] Times in correct timezone
- [ ] P&L calculations accurate
- [ ] Summary metrics correct
- [ ] Exit reasons accurate

## Performance Testing

- [ ] Backtest handles large CSV files (100K+ bars)
- [ ] Live trading remains responsive
- [ ] Memory usage reasonable
- [ ] No memory leaks during long runs
- [ ] Logs don't grow excessively

## Error Handling

- [ ] Invalid CSV format handled gracefully
- [ ] Missing .env handled with clear error
- [ ] IG authentication failure handled
- [ ] Network disconnection handled (Lightstreamer)
- [ ] Invalid configuration values caught

## Documentation Review

- [ ] README.md complete and accurate
- [ ] QUICKSTART.md easy to follow
- [ ] Code comments clear and helpful
- [ ] Configuration options documented
- [ ] CLI options documented

## Final Checklist

- [ ] All backtest tests passing
- [ ] Dry run mode working correctly
- [ ] Reports generated accurately
- [ ] No errors in logs
- [ ] Strategy logic verified
- [ ] Ready for real historical data testing
- [ ] Ready for live Demo testing (with monitoring)

## Notes

Use this space to record any issues, observations, or results:

```
Date: ___________
Tester: ___________

Backtest Results (TP=5):
- Total Trades: ___
- Win Rate: ___%
- Total P&L: ___ pts

Backtest Results (TP=10):
- Total Trades: ___
- Win Rate: ___%
- Total P&L: ___ pts

Dry Run Observations:
-

Live Demo Results (if tested):
-

Issues Found:
-

Recommendations:
-
```
