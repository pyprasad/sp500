# RSI-2 Rebound Strategy - Multi-Market Trading

A simple, deterministic RSI-2 rebound long strategy for multiple markets (US500, GERMANY40, etc.) on IG Demo account with offline backtesting capabilities.

## Overview

This project implements a systematic trading strategy that:
- Uses RSI(2) indicator with oversold threshold of 3
- Enters long positions when RSI rebounds (crosses above 3 after being at/below 3)
- Supports multiple markets with market-specific configurations
  - **US500**: NYSE hours (09:30-16:00 ET), 0.6 pt spread
  - **GERMANY40**: XETRA hours (09:00-17:30 CET), 1.0 pt spread
  - Easily extensible to other markets via config.yaml
- Skips the first 30 minutes of each session (configurable)
- Tests two take-profit configurations: 5 pts and 10 pts
- Uses a 2-point stop loss (configurable)
- Enforces single position at a time
- Closes positions by EOD if targets not hit

## Project Structure

```
ig-us500-rsi2/
├── README.md                 # This file
├── CLAUDE.md                 # Claude Code instructions
├── .env.example              # Environment variables template
├── requirements.txt          # Python dependencies
├── config.yaml               # Strategy configuration
├── src/
│   ├── __init__.py
│   ├── main.py              # Live trading CLI
│   ├── backtest.py          # Backtest CLI
│   ├── ig_auth.py           # IG API authentication
│   ├── ig_stream.py         # Lightstreamer integration
│   ├── candle_builder.py    # Tick-to-candle aggregation
│   ├── indicators.py        # RSI calculation
│   ├── session_clock.py     # Trading hours management
│   ├── strategy.py          # Strategy logic
│   ├── broker.py            # Order execution
│   ├── risk.py              # Risk management
│   ├── trade_log.py         # Trade logging
│   ├── bt_engine.py         # Backtest engine
│   ├── bt_reports.py        # Backtest reporting
│   └── utils.py             # Utilities
├── data/
│   ├── ticks/               # Live tick data
│   ├── candles/             # Live 30-min bars
│   ├── trades/              # Live trade log
│   └── backtest/            # Historical CSVs for backtesting
│       ├── sample_us500_30m.csv     # Sample US500 data
│       └── germany40/               # Germany40 market data
│           └── dax_2012-*.csv       # Monthly DAX data files
├── reports/
│   └── backtest/            # Backtest results
└── logs/                    # Runtime logs
```

## Installation

### 1. Clone or Setup

```bash
cd /path/to/ig-us500-rsi2
```

### 2. Install Dependencies

```bash
# Use pip or pip3 depending on your system
pip install -r requirements.txt
# or
pip3 install -r requirements.txt
```

Required packages:
- requests >= 2.31.0
- pandas >= 2.0.0
- numpy >= 1.24.0
- python-dotenv >= 1.0.0
- pyyaml >= 6.0
- pytz >= 2023.3
- lightstreamer-client-lib >= 1.0.3

**Note:** On macOS and some Linux systems, use `python3` and `pip3` instead of `python` and `pip`.

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your IG Demo credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
IG_API_KEY=your_demo_key
IG_USERNAME=your_demo_user
IG_PASSWORD=your_demo_pass
IG_ACCOUNT_TYPE=DEMO
IG_ACCOUNT_ID=ABC123
```

**Important:** Never commit your `.env` file to version control!

### 4. Verify Configuration

Review `config.yaml` and adjust if needed:
- `default_market`: Default market to trade (US500 or GERMANY40)
- `rsi_period`: RSI period (default: 2)
- `oversold`: Oversold threshold (default: 3.0)
- `stop_loss_pts`: Stop loss in points (default: 2.0)
- `take_profits_pts`: TP variants to test (default: [5.0, 10.0])
- `dry_run`: Set to `false` to execute real trades on Demo

Market-specific settings (in `markets` section):
- `symbol`: Display name (e.g., "US 500", "Germany 40")
- `epic`: IG instrument code (e.g., IX.D.SPTRD.DAILY.IP)
- `tz`: Market timezone (e.g., "America/New_York", "Europe/Berlin")
- `session_open`: Market open time (e.g., "09:30", "09:00")
- `session_close`: Market close time (e.g., "16:00", "17:30")
- `spread_assumption_pts`: Spread assumption (e.g., 0.6, 1.0)

## Usage

### Backtesting

Run backtest on historical candle data. Use `python3` on macOS/Linux or `python` on Windows.

#### US500 Backtesting

```bash
# Backtest US500 with 5-point take profit
python3 -m src.backtest --data-path data/backtest --market US500 --tp 5

# Backtest US500 with 10-point take profit
python3 -m src.backtest --data-path data/backtest --market US500 --tp 10

# Backtest single CSV file
python3 -m src.backtest --data-path data/backtest/us500_30m.csv --market US500 --tp 5

# Show detailed trade information
python3 -m src.backtest --data-path data/backtest --market US500 --tp 5 --show-trades
```

#### GERMANY40 Backtesting

```bash
# Backtest GERMANY40 with 5-point take profit
python3 -m src.backtest --data-path data/backtest/germany40 --market GERMANY40 --tp 5

# Backtest GERMANY40 with 10-point take profit
python3 -m src.backtest --data-path data/backtest/germany40 --market GERMANY40 --tp 10

# Override market-specific settings
python3 -m src.backtest --data-path data/backtest/germany40 --market GERMANY40 --tp 5 \
  --tz Europe/Berlin --spread 1.0 --sl 2.0 \
  --open 09:00 --close 17:30 --skip-first 30

# Custom output directory
python3 -m src.backtest --data-path data/backtest/germany40 --market GERMANY40 --tp 10 \
  --out reports/backtest/germany40
```

#### Using Default Market

If `default_market` is set in config.yaml, you can omit `--market`:

```bash
# Uses default_market from config.yaml
python3 -m src.backtest --data-path data/backtest --tp 5
```

#### Backtest Options

```
--data-path PATH      Path to CSV file or directory (required)
--tp POINTS           Take profit in points (required)
--market MARKET       Market to backtest (US500, GERMANY40, etc.)
--rsi-period N        RSI period (default from config)
--timeframe SECONDS   Candle timeframe in seconds (default from config)
--sl POINTS           Stop loss in points (default from config)
--spread POINTS       Spread assumption (default from market config)
--tz TIMEZONE         Timezone (default from market config)
--open HH:MM          Session open time (default from market config)
--close HH:MM         Session close time (default from market config)
--skip-first MIN      Skip first N minutes (default from config)
--out DIR             Output directory (default: reports/backtest)
--config PATH         Config file path (default: config.yaml)
--show-trades         Print detailed trade information
```

#### CSV Format

Your historical data CSVs should have OHLC columns. The backtest engine automatically handles common column name variations:

**Required columns** (case-insensitive, various names accepted):
- **Timestamp**: `timestamp`, `datetime`, `date`, `time` - ISO format datetime (UTC or with timezone)
- **Open**: `open` - Open price
- **High**: `high` - High price
- **Low**: `low` - Low price
- **Close**: `close` - Close price
- **Volume**: `volume` - Volume (optional, defaults to 0 if missing)

**Supported CSV formats:**

Format 1 (lowercase):
```csv
timestamp,open,high,low,close,volume
2024-01-02 09:30:00,4750.25,4755.50,4748.00,4753.75,1000
2024-01-02 10:00:00,4753.75,4760.00,4751.25,4758.50,950
```

Format 2 (capitalized, no volume - like Germany40 data):
```csv
Datetime,Open,High,Low,Close
2012-01-20 08:30:00+00:00,6410.74,6415.32,6408.12,6412.50
2012-01-20 09:00:00+00:00,6412.50,6420.15,6410.20,6418.75
```

**Notes:**
- Column names are automatically normalized to lowercase
- `Datetime` is automatically mapped to `timestamp`
- Volume column is optional (set to 0 if missing)
- Timestamps can be in any timezone (converted to market timezone during backtest)
- Data can be any timeframe (aggregated to configured timeframe during backtest)

#### Backtest Outputs

Results are saved to `reports/backtest/`:

1. **trades_tp{N}.csv**: Per-trade details
   - Entry/exit times (UTC and NY time)
   - Entry/exit prices
   - TP/SL levels
   - Exit reason (TP/SL/EOD)
   - P&L in points and GBP
   - Bars held

2. **equity_tp{N}.csv**: Equity curve
   - Datetime
   - Cumulative equity in points
   - Cumulative equity in GBP

3. **summary_tp{N}.csv**: Aggregate metrics
   - Total trades
   - Win rate
   - Average win/loss
   - Payoff ratio
   - Expectancy
   - Total P&L
   - Max drawdown
   - Average bars held
   - Exit reason counts

### Live Trading

Run live trading on IG Demo. Use `python3` on macOS/Linux or `python` on Windows.

#### US500 Live Trading

```bash
# Trade US500 with 5-point take profit (uses default market if not specified)
python3 -m src.main --tp 5

# Trade US500 with 10-point take profit
python3 -m src.main --tp 10

# Explicitly specify US500 market
python3 -m src.main --market US500 --tp 5
```

#### GERMANY40 Live Trading

```bash
# Trade GERMANY40 with 5-point take profit
python3 -m src.main --market GERMANY40 --tp 5

# Trade GERMANY40 with 10-point take profit
python3 -m src.main --market GERMANY40 --tp 10

# Override RSI period and timeframe
python3 -m src.main --market GERMANY40 --tp 10 --rsi-period 3 --timeframe 900
```

**Important Notes:**

1. **Dry Run Mode**: By default, `dry_run: true` in `config.yaml`. The system will:
   - Connect to IG and stream live data
   - Build candles and compute RSI
   - Generate signals and log trades
   - **NOT execute real orders**

2. **Live Trading**: To execute real orders on Demo:
   - Set `dry_run: false` in `config.yaml`
   - Ensure you understand the risks
   - Monitor the system actively

3. **Data Storage**:
   - Ticks: `data/ticks/ticks_YYYYMMDD_HHMMSS.csv`
   - Candles: `data/candles/candles_YYYYMMDD.csv`
   - Trades: `data/trades/trades.csv`
   - Logs: `logs/runtime_YYYYMMDD_HHMMSS.log`

4. **Graceful Shutdown**:
   - Press `Ctrl+C` to stop
   - System will close open positions
   - Disconnect from Lightstreamer
   - Print trade summary

## Strategy Rules

### Entry Rules

1. **Indicator**: RSI(2) on 30-minute bars
2. **Setup**: Track when RSI ≤ 3.0 (oversold condition)
3. **Trigger**: Enter long when RSI crosses above 3.0 after being at/below 3.0
4. **Timing**: Only during 10:00-15:59 ET (skip first 30 min, allow time to close)
5. **Concurrency**: Maximum one position at a time
6. **Entry Price**: Ask price (open + spread/2 for backtest)

### Exit Rules

1. **Take Profit**: Exit when bid reaches entry + TP points
   - Test configurations: 5 pts and 10 pts
2. **Stop Loss**: Exit when bid reaches entry - 2 pts
3. **EOD Exit**: Force flat before 16:00 ET if neither TP nor SL hit
4. **Same-Bar Logic** (backtest): If both TP and SL hit same bar, SL exits first (conservative)

### Risk Management

- **Spread**: 0.6 pt assumption (enter at ask, exit at bid)
- **Position Size**: 1.0 GBP per point (configurable)
- **Stop Loss**: 2.0 pts (configurable)
- **Session Discipline**: Flat overnight, reset daily state

### RSI Calculation Method

This implementation uses **Wilder's Smoothing Method** for RSI calculation, which matches the standard used by IG, TradingView, MetaTrader, and other professional platforms.

**How Wilder's RSI works:**

1. **Calculate price changes** for each candle
2. **Separate gains and losses**:
   - Gain = change if positive, else 0
   - Loss = |change| if negative, else 0
3. **First average** (at bar N = RSI period):
   - `avg_gain = mean(first N gains)`
   - `avg_loss = mean(first N losses)`
4. **Subsequent averages** use exponential smoothing:
   - `new_avg_gain = (1/N) × current_gain + ((N-1)/N) × prev_avg_gain`
   - `new_avg_loss = (1/N) × current_loss + ((N-1)/N) × prev_avg_loss`
5. **Calculate RS and RSI**:
   - `RS = avg_gain / avg_loss`
   - `RSI = 100 - (100 / (1 + RS))`

**Key characteristics:**
- For RSI(2), smoothing factor alpha = 1/2 = 0.5
- Exponential decay incorporates ALL historical price data
- More stable than simple moving average approaches
- **Matches IG platform values** when sufficient history is available

**Cold Start Handling:**

The system attempts to pre-load 50 historical candles from IG API at startup to ensure accurate RSI from the beginning. If historical data is unavailable (e.g., API limits exceeded), RSI will "warm up" as live candles accumulate:

- **Minimum for calculation**: 3 candles (RSI period + 1)
- **Recommended minimum**: 20 candles for reliable signals
- **Full confidence**: 50+ candles

Configuration in `config.yaml`:
```yaml
preload_candles: 50          # Number of historical bars to fetch at startup
min_candles_for_trading: 20  # Minimum candles before RSI is considered reliable
```

## Architecture

### Live Trading Flow

1. **Authentication**: `ig_auth.py` authenticates with IG REST API
2. **Streaming**: `ig_stream.py` subscribes to Lightstreamer tick feed
3. **Candle Building**: `candle_builder.py` aggregates ticks into 30-min bars
4. **Indicators**: `indicators.py` computes RSI(2) on completed bars
5. **Strategy**: `strategy.py` detects oversold rebound signals
6. **Session**: `session_clock.py` enforces US market hours and timing rules
7. **Risk**: `risk.py` calculates entry/exit levels with spread
8. **Broker**: `broker.py` executes orders via IG REST API
9. **Logging**: `trade_log.py` logs trades to CSV and console

### Backtest Flow

1. **Data Loading**: `bt_engine.py` loads CSV(s) from `data/backtest/`
2. **Timezone Conversion**: Converts timestamps to America/New_York
3. **Session Filtering**: Keeps only bars within 09:30-16:00 ET
4. **Entry Filtering**: Allows entries only 10:00-15:59:30 ET
5. **RSI Calculation**: Computes RSI(2) on close prices
6. **Signal Detection**: Same rebound logic as live (oversold → crossover)
7. **Spread Modeling**:
   - Entry: bar open + spread/2 (ask)
   - TP check: bar high ≥ entry + TP (bid reach)
   - SL check: bar low ≤ entry - SL (bid reach)
   - EOD exit: bar close - spread/2 (bid)
8. **Conservative Exits**: SL before TP if both hit same bar
9. **Reporting**: `bt_reports.py` generates trades, equity, summary

## Configuration Reference

### config.yaml

```yaml
# Global strategy parameters
timeframe_sec: 1800                    # 30 minutes
rsi_period: 2                          # RSI period
oversold: 3.0                          # Oversold threshold

take_profits_pts: [5.0, 10.0]         # TP variants to test
stop_loss_pts: 2.0                     # Stop loss

size_gbp_per_point: 1.0                # Position size
only_long: true                        # Long-only strategy
one_position_at_a_time: true           # Single position concurrency
dry_run: true                          # Dry run mode (no real orders)
log_level: "INFO"                      # Logging level

# Market-specific configurations
markets:
  US500:
    symbol: "US 500"
    epic: "IX.D.SPTRD.DAILY.IP"
    tz: "America/New_York"
    session_open: "09:30"
    session_close: "16:00"
    no_trade_first_minutes: 30
    spread_assumption_pts: 0.6

  GERMANY40:
    symbol: "Germany 40"
    epic: "IX.D.DAX.DAILY.IP"
    tz: "Europe/Berlin"
    session_open: "09:00"
    session_close: "17:30"
    no_trade_first_minutes: 30
    spread_assumption_pts: 1.0

# Default market (used if --market not specified)
default_market: "US500"
```

**Adding New Markets:**

To add a new market (e.g., UK100), add an entry to the `markets` section:

```yaml
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
python3 -m src.backtest --data-path data/backtest/uk100 --market UK100 --tp 5
```

## Development

### Running Tests

Currently no automated tests. Manual testing recommended:

1. **Backtest Validation**:
   - Create sample CSV with known patterns
   - Verify trades match expected entries/exits
   - Check summary metrics

2. **Live Testing**:
   - Run in dry_run mode first
   - Verify candle building
   - Check RSI calculations
   - Confirm signals match expectations

### Debugging

Enable DEBUG logging in `config.yaml`:

```yaml
log_level: "DEBUG"
```

Logs include:
- Tick reception
- Candle completion
- RSI values
- Oversold detection
- Signal generation
- Order execution
- Trade results

## Troubleshooting

### Authentication Fails

- Verify IG credentials in `.env`
- Ensure using DEMO account
- Check API key is valid
- Confirm network connectivity

### No Ticks Received

- Check IG account is active
- Verify epic code is correct
- Ensure market is open
- Review Lightstreamer connection logs

### Backtest Shows No Trades

- Verify CSV format (required columns)
- Check timestamps are in valid range
- Ensure data covers US market hours
- Review RSI calculation (need enough data)

### Different Results: Live vs Backtest

Possible reasons:
- Spread modeling differences
- Tick-level fills vs OHLC simulation
- Timing precision (real-time vs bar-close)
- This is expected and normal for tick vs bar simulation

## Safety and Risk Warnings

1. **Demo Account Only**: This code is designed for IG Demo accounts
2. **No Warranties**: Use at your own risk, no guarantees of profitability
3. **Test Thoroughly**: Always test in dry_run mode before live execution
4. **Monitor Actively**: Don't leave live trading unattended
5. **Understand the Strategy**: Ensure you fully understand the logic and risks
6. **Check Credentials**: Never commit `.env` file or share API keys
7. **Market Conditions**: Strategy performance depends on market conditions
8. **Spread and Slippage**: Real fills may differ from backtest assumptions

## Backtest Results

**IMPORTANT:** These are REALISTIC backtest results with proper modeling of:
- No look-ahead bias (enter at NEXT bar, not same bar as signal)
- Proper spread accounting (entry at ask, exit at bid)
- Conservative TP/SL checks against bid prices

Results from backtesting on GERMANY40 (full year 2024, 11,401 bars):

### GERMANY40 Performance - REALISTIC MODELING

#### TP = 5 pts, SL = 30 pts, Spread = 2 pts
- **Total Trades**: 232
- **Win Rate**: 72.41% (168 wins / 64 losses)
- **Expectancy**: -4.418 pts per trade ⚠️
- **Total P&L**: -1,025.08 pts / -2,050.16 GBP
- **Max Drawdown**: -1,035.08 pts
- **Avg Win**: 5.000 pts
- **Avg Loss**: -29.142 pts
- **Avg Bars Held**: 1.2
- **Exit Breakdown**: 168 TP / 61 SL / 3 EOD

#### TP = 10 pts, SL = 30 pts, Spread = 2 pts
- **Total Trades**: 232
- **Win Rate**: 68.97% (160 wins / 72 losses)
- **Expectancy**: -1.994 pts per trade ⚠️
- **Total P&L**: -462.56 pts / -925.12 GBP
- **Max Drawdown**: -687.13 pts
- **Avg Win**: 9.966 pts
- **Avg Loss**: -28.571 pts
- **Avg Bars Held**: 1.3
- **Exit Breakdown**: 159 TP / 67 SL / 6 EOD

#### TP = 12 pts, SL = 30 pts, Spread = 2 pts
- **Total Trades**: 232
- **Win Rate**: 65.95% (153 wins / 79 losses)
- **Expectancy**: -1.875 pts per trade ⚠️
- **Total P&L**: -435.04 pts / -870.09 GBP
- **Max Drawdown**: -676.11 pts
- **Avg Win**: 11.880 pts
- **Avg Loss**: -28.514 pts
- **Avg Bars Held**: 1.4
- **Exit Breakdown**: 151 TP / 73 SL / 8 EOD

### Key Observations

**Strategy Performance:**
- ⚠️ **ALL configurations show NEGATIVE expectancy** with current parameters
- TP=12 performs best (least negative: -1.875 pts/trade vs -4.418 for TP=5)
- Win rates 66-72% are decent but insufficient to overcome large losses
- **Risk/Reward imbalance**: Avg loss (28-29 pts) >> Avg win (5-12 pts)

**Why the Strategy Struggles:**
1. **Spread impact**: 2 pts spread on GERMANY40 is significant relative to 5-10 pt TP
2. **Large stop loss**: 30 pt SL vs 5-12 pt TP creates poor risk/reward (1:6 to 1:2.5 ratio)
3. **Market noise**: RSI-2 on 30-min bars generates many false signals
4. **No look-ahead bias**: Realistic entry timing reduces opportunities

**Potential Improvements to Explore:**
- Reduce stop loss to 10-15 pts for better risk/reward
- Increase TP to 15-20 pts to improve payoff ratio
- Tighten oversold threshold (e.g., RSI < 5 instead of < 10)
- Add trend filter (only trade in direction of longer-term trend)
- Test on markets with lower spread (US500 has 0.6 pt spread vs GERMANY40's 2 pts)
- Consider position sizing based on volatility

**Comparison: Unrealistic vs Realistic Results**

| Metric | Old (Unrealistic) TP=10 | New (Realistic) TP=10 | Difference |
|--------|------------------------|---------------------|------------|
| Total Trades | 246 | 232 | -14 trades |
| Win Rate | 90.65% | 68.97% | -21.68% |
| Expectancy | +6.222 pts | -1.994 pts | -8.216 pts |
| Total P&L | +1,530.51 pts | -462.56 pts | **-1,993 pts** |

The unrealistic backtest was showing **false profitability** due to look-ahead bias and improper spread modeling.

## Support and References

### IG API Documentation

- [IG REST API](https://labs.ig.com/rest-trading-api-reference)
- [IG Streaming API](https://labs.ig.com/streaming-api-guide)

### Lightstreamer Client

- [Python Client Docs](https://lightstreamer.com/sdks/ls-python-client/1.0.3/api/index.html)

### Strategy Reference

- RSI indicator: Relative Strength Index by J. Welles Wilder
- Mean reversion: Short-term oversold rebounds

## License

This project is provided as-is for educational and research purposes.

## Changelog

### v1.2.0 - Realistic Backtest Modeling (2025-11-06)

- **CRITICAL FIX: Eliminated look-ahead bias in backtest**
  - Previous version entered at same bar as signal (unrealistic)
  - Now enters at NEXT bar's open after signal (realistic)
  - This is a MAJOR fix that significantly impacts results
- **Fixed spread modeling in backtest**
  - Entry at ask price: `open + spread/2`
  - Exit at bid prices: TP check uses `high - spread/2`, SL check uses `low - spread/2`
  - Previously checked against mid prices (overstated profits)
- **Realistic P&L calculation**
  - Properly accounts for entry/exit spreads
  - TP exits now achieve exact TP points (not TP + spread)
- **Updated backtest results with realistic modeling**
  - GERMANY40 2024: Strategy shows NEGATIVE expectancy with current parameters
  - Identified need for better risk/reward ratio (30pt SL vs 5-12pt TP is poor)
  - Added comparison table showing unrealistic vs realistic results
  - Previous results were inflated by ~2,000 pts due to biases
- **Documentation improvements**
  - Added detailed explanation of backtest modeling assumptions
  - Added strategy improvement suggestions
  - Enhanced changelog with technical details

### v1.1.0 - Wilder's RSI Implementation (2025-11-06)

- **Fixed RSI calculation** to use Wilder's exponential smoothing method
  - Now matches IG platform, TradingView, MT4, and other professional platforms
  - Previously used simple moving average (less accurate)
  - Exponential smoothing incorporates ALL historical price data with decay
- **Added historical data pre-loading** from IG API at startup
  - Fetches 50 candles for accurate RSI from the beginning
  - Graceful fallback if API limits exceeded (cold start mode)
  - Configurable via `preload_candles` in config.yaml
- **Multi-market support enhancements**
  - Enabled GERMANY40 configuration in config.yaml
  - Verified backtest results with corrected RSI method
- **Documentation improvements**
  - Added RSI calculation method explanation
  - Added backtest performance results
  - Enhanced CSV format documentation

### v1.0.0 - Initial Release

- RSI-2 rebound strategy implementation
- Live trading via IG Demo + Lightstreamer
- Offline backtesting from CSV data
- Two TP variants (5 pts, 10 pts)
- Session-aware trading (US market hours)
- Dry run and live execution modes
- Comprehensive logging and reporting
