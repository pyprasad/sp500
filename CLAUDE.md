# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSI-2 rebound long strategy for multiple markets (US500, GERMANY40, etc.) on IG Demo with offline backtesting from local CSVs.

**Strategy rules:**
- RSI (default period = 2) with oversold threshold = 3
- Enter long when RSI crosses up through 3 after being at/under 3
- Configurable timeframes (default: 30-minute bars)
- Market-specific hours and timezones
- No trading first 30 minutes after session open, flat by EOD
- Test two configs: TP = 5 pts and TP = 10 pts
- SL = 2.0 pts (configurable)
- Market-specific spread assumptions
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
reports/
  backtest/      # Backtest results (trades, equity, summary per TP variant)
```

## Important Constraints

- **Single position**: Ignore signals while position is open
- **Deterministic exits**: In backtest, if both TP and SL hit same bar, SL exits first
- **EOD discipline**: Always flat by 16:00 ET (live) or last bar of session (backtest)
- **No overfitting**: Keep strategy simple, deterministic, and transparent
