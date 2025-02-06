__version__ = "0.0.1"

from gymnasium.envs.registration import register

register(
    id='ElectricityMarketEnv-v0',
    entry_point='electricity_market.electricity_market_env:ElectricityMarketEnv',
)