from src.bt_engine import BacktestEngine
from src.indicators import compute_rsi
from src.utils import load_config, get_market_config
import pandas as pd

config = load_config('config.yaml')
config = get_market_config(config, 'GERMANY40')

engine = BacktestEngine(config)
df = engine.load_data('data/backtest/germany40')
df = engine.filter_session_bars(df)

rsi = compute_rsi(df['close'], config.get('rsi_period', 2))
df['rsi'] = rsi
df['rsi_prev'] = df['rsi'].shift(1)
df['signal'] = (
    (df['rsi_prev'] <= 5.0) & (df['rsi'] > 5.0) & (df['entry_allowed'])
)

print("Testing different trailing activations with distance=10:\n")
for activation in [10, 15, 20, 25, 30]:
    config['use_trailing_stop'] = True
    config['trailing_stop_activation_pts'] = activation
    config['trailing_stop_distance_pts'] = 10
    
    test_engine = BacktestEngine(config)
    results = test_engine.run_backtest(df.copy(), 40)
    
    if results:
        trades_df = pd.DataFrame(results)
        total_pnl = trades_df['pnl_pts'].sum()
        print(f"Activation={activation:2d}: P&L={total_pnl:+8.2f} pts")
