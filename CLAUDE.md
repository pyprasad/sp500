# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSI-2 rebound long strategy for multiple markets (US500, GERMANY40, etc.) on IG Demo with offline backtesting from local CSVs.

**Strategy rules:**
- RSI (default period = 2) with oversold threshold = 5
- Enter long when RSI crosses up through threshold after being at/under threshold
- Configurable timeframes (default: 30-minute bars)
- Market-specific hours and timezones
- No trading first 30 minutes after session open
- **EOD policy**: Configurable (force exit or allow overnight holds)
- **Trailing stop**: Optional (activation=25 pts, distance=10 pts → +1,244 pts in backtest!)
- TP = 40 pts, SL = 100 pts (configurable)
- Market-specific spread assumptions (with off-hours multiplier)
- **Overnight charges**: Simulated in backtest (percentage-based)
- One position at a time

**Supported Markets:**
- US500: NYSE hours (09:30-16:00 ET), spread 0.6 pts
- GERMANY40: XETRA hours (09:00-17:30 CET), spread 1.0 pts
- Easily extensible to other markets via config.yaml

## Commands

### Live Trading (IG Demo)
```bash
# Run US500 with default settings
python -m src.main --tp 5

# Run GERMANY40
python -m src.main --market GERMANY40 --tp 10

# Override RSI period and timeframe
python -m src.main --market US500 --tp 5 --rsi-period 3 --timeframe 900

# Custom config file
python -m src.main --market GERMANY40 --tp 5 --config custom_config.yaml
```

### Backtesting
```bash
# US500 (default market)
python -m src.backtest --data-path data/backtest --tp 5

# GERMANY40
python -m src.backtest --data-path data/backtest/germany40 --market GERMANY40 --tp 10

# Override RSI period and timeframe
python -m src.backtest --data-path data/backtest --market US500 --tp 5 \
  --rsi-period 3 --timeframe 900

# Override market-specific settings
python -m src.backtest --data-path data/backtest --market GERMANY40 --tp 5 \
  --tz Europe/Berlin --spread 1.0 --sl 2.0 \
  --open 09:00 --close 17:30 --skip-first 30 \
  --out reports/backtest/germany40
```

## Architecture

### Live Trading Flow
1. **ig_auth.py**: Authenticates with IG API, manages CST/X-SECURITY tokens
2. **ig_stream.py**: Connects to Lightstreamer, subscribes to tick data
3. **candle_builder.py**: Aggregates ticks into 30-min bars (mid = (bid+ask)/2)
4. **indicators.py**: Computes RSI(2) on completed bars
5. **strategy.py**: Implements rebound logic (oversold detection + crossover entry)
6. **session_clock.py**: Enforces US market hours, no-trade first 30 minutes, EOD flat
7. **broker.py**: Executes orders via IG REST API
8. **risk.py**: Manages TP/SL in points (ask entry, bid exits)
9. **trade_log.py**: Logs trades to CSV and console

### Backtest Flow
1. **bt_engine.py**: Core simulator
   - Loads CSV(s) from `data/backtest/`
   - Converts timestamps to America/New_York timezone
   - Filters bars to session hours (09:30-16:00 ET)
   - Skips first 30 minutes (entries start 10:00 ET)
   - Computes RSI(2) on close prices
   - Models spread: entry at `open + spread/2`, exits at `high/low` for TP/SL checks
   - Same-bar TP & SL: SL triggers first (conservative)
   - EOD exit: close at last bar's `close - spread/2`
   - One position at a time
2. **bt_reports.py**: Generates metrics and equity curves
   - `trades_tp{N}.csv`: per-trade details
   - `equity_tp{N}.csv`: equity curve
   - `summary_tp{N}.csv`: aggregate stats (win rate, expectancy, drawdown, etc.)

### Key Design Patterns

**Rebound detection:**
- Set `seen_oversold = True` when RSI ≤ 3
- Enter when `seen_oversold` and RSI > 3 (crossover)
- Reset `seen_oversold = False` after entry

**Spread modeling (backtest):**
- Entry: `bar.open + spread_pts/2` (ask)
- TP check: `bar.high >= entry + tp_pts` (bid reach)
- SL check: `bar.low <= entry - sl_pts` (bid reach)
- EOD exit: `bar.close - spread_pts/2` (bid)

**Session filtering:**
- Convert all bar timestamps to market-specific timezone (from config)
- Allow entries only after `no_trade_first_minutes` from session open
- Force flat by last bar before session close

## Configuration

- **.env**: IG API credentials (use `.env.example` as template)
- **config.yaml**: Multi-market configuration
  - Global parameters: RSI period, oversold threshold, TP/SL, timeframe
  - Market-specific settings: symbol, EPIC, timezone, session hours, spread
  - Add new markets by adding entries to the `markets` section
  - Set `default_market` to specify which market to use when `--market` not provided

### Adding New Markets

To add a new market (e.g., UK100), add an entry to the `markets` section in `config.yaml`:

```yaml
markets:
  UK100:
    symbol: "FTSE 100"
    epic: "IX.D.FTSE.DAILY.IP"
    tz: "Europe/London"
    session_open: "08:00"
    session_close: "16:30"
    no_trade_first_minutes: 30
    spread_assumption_pts: 0.8
```

Then run with `--market UK100`:
```bash
python -m src.backtest --data-path data/backtest/uk100 --market UK100 --tp 5
```

## Data Structure

```
data/
  ticks/         # Live tick data
  candles/       # Live 30m bars
  trades/        # Live trade log
  backtest/      # Local 30m CSVs (timestamp, open, high, low, close, volume)
  spreads/       # Spread monitoring logs (BID/OFFER spread over time)
  state/         # Trade state persistence (crash recovery)
reports/
  backtest/      # Backtest results (trades, equity, summary per TP variant)
```

## EOD Exit Policy & Overnight Positions

### Configuration
Control whether positions are forced to close at end-of-day or allowed to hold overnight:

```yaml
# config.yaml
force_eod_exit: true   # true = close by EOD (conservative), false = allow overnight
max_hold_days: 0       # Max days to hold (0 = unlimited, e.g., 3-5 for safety)
```

### Overnight Funding Charges
When positions are held overnight, funding charges are applied (simulated in backtest, real in live trading):

```yaml
# Global default (can be overridden per market)
overnight_funding_rate_pct: 0.035  # 3.5% annual (~0.96 pts/day for DAX @16700)

# Market-specific override
markets:
  GERMANY40:
    overnight_funding_rate_pct: 0.035  # Check IG platform for current rates
```

**Calculation**: `Daily charge = (Entry price × Annual rate × Days held) / 365`

### Off-Hours Spread Simulation
Spreads widen during off-hours (nights/weekends). Backtest simulates this:

```yaml
markets:
  GERMANY40:
    spread_assumption_pts: 2.0  # Normal market hours spread
    off_hours_spread_multiplier: 2.5  # Off-hours spread = 2.0 × 2.5 = 5.0 pts
```

### Testing EOD vs Overnight
Compare results with different EOD policies:

```bash
# Test 1: Force EOD exit (current behavior, conservative)
# config.yaml: force_eod_exit: true
python -m src.backtest --data-path data/backtest --market GERMANY40 --tp 40 \
  --out reports/backtest/eod_exit

# Test 2: Allow overnight holds (higher profit potential, higher risk)
# config.yaml: force_eod_exit: false
python -m src.backtest --data-path data/backtest --market GERMANY40 --tp 40 \
  --out reports/backtest/overnight_allowed

# Compare results:
# - Total P&L (net of overnight charges)
# - Win rate
# - Avg days held
# - Total overnight charges paid
# - Max drawdown
```

**Key metrics in reports:**
- `Avg Days Held`: Average number of days positions were held
- `Total Overnight Charges`: Total funding charges paid (pts)
- `Positions Held Overnight`: Count of positions held >1 day

## Spread Monitoring & Safety

### Real-Time Spread Logging
Monitor and log BID/OFFER spreads during live trading:

```yaml
log_spreads: true  # Enable spread monitoring
spread_log_interval_sec: 300  # Log every 5 minutes (medium frequency)
spread_log_path: "data/spreads"  # Output directory
max_entry_spread_pts: 4.0  # Safety: refuse entry if spread > 4 pts (2x normal)
```

**Spread log format** (`data/spreads/IX.D.DAX.DAILY.IP_spread_log.csv`):
```csv
timestamp,bid,offer,spread_pts,market_open,notes
2025-11-08 09:00:00,16700.0,16702.0,2.0,true,market_open
2025-11-08 12:30:15,16720.5,16722.5,2.0,true,scheduled_log
2025-11-08 17:30:00,16735.0,16737.0,2.0,true,market_close
2025-11-08 18:00:00,16735.0,16740.0,5.0,false,wide_spread_warning_5.00pts
```

### Entry Safety Check
Spread monitor blocks entries if spread too wide (prevents bad fills during volatility/news):

- Configured via `max_entry_spread_pts` (default: 4.0 pts = 2x normal for DAX)
- Applies even during market hours (safety during news spikes)
- Logs warning: `Entry blocked: spread 5.50 pts exceeds max 4.0 pts`

### Use Cases for Spread Data
1. **Validate assumptions**: Check if `off_hours_spread_multiplier: 2.5` is accurate
2. **Risk management**: Identify dangerous trading times (wide spreads = higher costs)
3. **Strategy optimization**: Decide if overnight holds are worth the wider spreads
4. **Debugging**: Understand why entries were blocked or fills were poor

## Important Constraints

- **Single position**: Ignore signals while position is open
- **Deterministic exits**: In backtest, if both TP and SL hit same bar, SL exits first
- **EOD discipline**: Configurable (force_eod_exit: true/false)
  - `true`: Always flat by session close (conservative, current default)
  - `false`: Allow overnight holds (test in backtest first!)
- **No overfitting**: Keep strategy simple, deterministic, and transparent
- **Spread awareness**: Block entries if spread too wide (max_entry_spread_pts)
