"""description: This module training and optimizing RL agents on the electricity market"""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/10_player.ipynb.

# %% auto 0
__all__ = ['N_TRAIN_EPISODES', 'N_TRAILS', 'TRAIN_SEEDS', 'EVALUATE_SEEDS', 'ENV_CONFIG', 'TENSORBOARD_PATH', 'LOGS_PATH',
           'QUICK_MODE', 'evaluation_data_per_agent', 'maskable_random_agent', 'a2c_agent', 'maskable_ppo_agent',
           'optimized_maskable_ppo_agent', 'expert_maskable_random_agent', 'expert_maskable_ppo_agent',
           'optimized_expert_maskable_ppo_agent', 'Agent', 'ModelAgent', 'MaskableAgent', 'MaskableModelAgent',
           'MaskableRandomAgent', 'A2CAgent', 'MaskablePPOAgent', 'is_action_safe', 'expert_knowledge_action_masks']

# %% ../nbs/10_player.ipynb 3
import pickle
import shutil
from abc import ABC
from pathlib import Path

import numpy as np
import optuna
import torch
import yaml
from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.policies import MaskableActorCriticPolicy
from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3 import A2C
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.monitor import Monitor
from tqdm.notebook import tqdm

from .env import ElectricityMarketEnv, EnvConfig
from .utils import EvaluationData

# %% ../nbs/10_player.ipynb 4
N_TRAIN_EPISODES = 3
N_TRAILS = 10
TRAIN_SEEDS = [
    111111,
    121212,
    123456,
    200000,
    217890,
    222222,
    224775,
    234567,
    253084,
    285234,
    312135,
    314831,
    333333,
    345678,
    406339,
    444444,
    471678,
    555555,
    562845,
    666666,
    701753,
    755460,
    761386,
    777777,
    789391,
    888888,
    993068,
    979797,
    987654,
    999999,
]
EVALUATE_SEEDS = [
    117127,
    136901,
    223246,
    243382,
    245720,
    248832,
    288598,
    374487,
    447331,
    447851,
    490428,
    553737,
    557309,
    571504,
    601426,
    632202,
    653634,
    844596,
    848937,
    849735,
    865470,
    866822,
    876563,
    880689,
    887591,
    911016,
    920528,
    963993,
    967995,
    992634,
]
ENV_CONFIG = EnvConfig()

TENSORBOARD_PATH = Path("../tensorboard")
LOGS_PATH = Path("../logs")

# Set QUICK_MODE = True for CI
QUICK_MODE = True

if QUICK_MODE:
    ENV_CONFIG = EnvConfig(max_timestep=10)
    TRAIN_SEEDS = [10000]
    EVALUATE_SEEDS = [90000]
    TENSORBOARD_PATH = None
    LOGS_PATH = None

evaluation_data_per_agent = {}

# %% ../nbs/10_player.ipynb 6
class Agent(ABC):
    def __init__(self, name, env, device):
        self.name = name
        self.device = device
        self.env = env

    def evaluate(self, render: bool = False) -> EvaluationData:
        """
        Evaluate the model, and return EvaluationData.
        """
        all_rewards = []

        for seed in tqdm(EVALUATE_SEEDS, desc="seeds"):
            obs, _ = self.env.reset(seed=seed)
            episode_rewards = []
            done = False

            while not done:
                obs_tensor = torch.tensor(obs, dtype=torch.float64).to(self.device)

                action = self.choose_action(obs_tensor)
                obs, reward, done, truncated, _ = self.env.step(action)
                episode_rewards.append(reward)

                if render:
                    self.env.render()

                if truncated:
                    break

            all_rewards.append(np.sum(episode_rewards))

        return EvaluationData(
            episodes=list(range(len(all_rewards))),
            rewards=all_rewards,
        )

    def choose_action(self, obs_tensor):
        raise NotImplementedError


class ModelAgent(Agent):
    def __init__(self, name, env, env_config, model, device):
        super().__init__(name, device=device, env=env)
        self.model = model
        self.env_config = env_config

    def train(self) -> None:
        """
        Train the model
        """
        checkpoint_callback = CheckpointCallback(save_freq=1000, save_path="../logs/")

        for seed in tqdm(TRAIN_SEEDS, desc="seeds"):
            for _ in tqdm(range(N_TRAIN_EPISODES), desc="Training episodes"):
                self.env.reset(seed=seed)
                self.model.learn(
                    total_timesteps=self.env_config.max_timestep,
                    callback=checkpoint_callback,
                    reset_num_timesteps=False,
                    tb_log_name=self.name,
                )

    def choose_action(self, obs_tensor):
        action, _ = self.model.predict(obs_tensor, deterministic=True)
        return action

    def save_model(self, model_path: Path) -> None:
        self.model.save(str(model_path))

    def load_model(self, model_path: Path) -> None:
        self.model = self.model.load(str(model_path), env=self.env)


class MaskableAgent(Agent):
    @staticmethod
    def mask_fn(env):
        """
        Placeholder mask function if needed.
        """
        return env.unwrapped.action_masks()


class MaskableModelAgent(MaskableAgent, ModelAgent):
    def choose_action(self, obs_tensor):
        action, _ = self.model.predict(
            obs_tensor,
            action_masks=MaskableAgent.mask_fn(self.env),
            deterministic=True,
        )

# %% ../nbs/10_player.ipynb 7
class MaskableRandomAgent(MaskableAgent):
    def __init__(
        self,
        env_config: EnvConfig | None = None,
        render_mode: str | None = None,
        name: str = "MaskableRandomAgent",
    ):
        """
        Initialize the agent and create the environment.
        """
        device = "cuda" if torch.cuda.is_available() else "cpu"
        env = ActionMasker(
            ElectricityMarketEnv(env_config, render_mode=render_mode), self.mask_fn
        )
        super().__init__(name, device=device, env=env)

    def choose_action(self, obs_tensor):
        action_mask = self.env.action_masks()
        valid_actions = np.where(action_mask)[0]
        action = np.random.choice(valid_actions)

        return action

# %% ../nbs/10_player.ipynb 8
class A2CAgent(ModelAgent):
    """A2C Agent for the Electricity Market Environment."""

    def __init__(
        self,
        env_config: EnvConfig | None = None,
        render_mode: str | None = None,
        name: str = "A2CAgent",
    ):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        env = Monitor(
            ElectricityMarketEnv(env_config, render_mode=render_mode),
        )
        model = A2C(
            "MlpPolicy",
            env,
            verbose=0,
            tensorboard_log=f"./tensorboard/",
            device=device,
        )
        super().__init__(
            name=name, env=env, model=model, device=device, env_config=env_config
        )

# %% ../nbs/10_player.ipynb 9
class MaskablePPOAgent(ModelAgent, MaskableAgent):
    """Maskable PPO Agent for the Electricity Market Environment."""

    def __init__(
        self,
        env_config: EnvConfig | None = None,
        render_mode: str | None = None,
        name: str = "MaskablePPOAgent",
    ):
        env = Monitor(
            ActionMasker(
                ElectricityMarketEnv(env_config, render_mode=render_mode),
                self.mask_fn,
            )
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = MaskablePPO(
            MaskableActorCriticPolicy,
            env,
            verbose=0,
            tensorboard_log=f"./tensorboard/",
            device=device,
        )
        super().__init__(
            name=name, env=env, model=model, device=device, env_config=env_config
        )
        self.optimized_hyperparameters = {}
        self.env_config = env_config or EnvConfig()

    def choose_action(self, obs_tensor):
        action, _ = self.model.predict(
            obs_tensor, deterministic=True, action_masks=MaskableAgent.mask_fn(self.env)
        )
        return action

    def optimize(self) -> None:
        """
        Optimize the agent with hyperparameters.
        """

        def objective(trial):
            learning_rate = trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True)
            n_steps = trial.suggest_int("n_steps", 32, 1024, log=True)
            batch_size = trial.suggest_int("batch_size", 16, 256, log=True)
            gae_lambda = trial.suggest_float("gae_lambda", 0.8, 1.0)
            ent_coef = trial.suggest_float("ent_coef", 0.0, 0.02)
            vf_coef = trial.suggest_float("vf_coef", 0.1, 1.0)
            clip_range = trial.suggest_float("clip_range", 0.1, 0.3)
            max_grad_norm = trial.suggest_float("max_grad_norm", 0.1, 1.0)

            agent = MaskablePPOAgent(
                self.env_config,
            )

            model = MaskablePPO(
                MaskableActorCriticPolicy,
                agent.env,
                learning_rate=learning_rate,
                n_steps=n_steps,
                batch_size=batch_size,
                gae_lambda=gae_lambda,
                ent_coef=ent_coef,
                vf_coef=vf_coef,
                clip_range=clip_range,
                max_grad_norm=max_grad_norm,
                verbose=0,
                device=self.device,
            )

            agent.model = model
            agent.train()

            return np.mean(agent.evaluate().rewards)

        study = optuna.create_study(
            study_name=self.name,
            storage="sqlite:///optuna_study.db",
            load_if_exists=True,
            direction="maximize",
            pruner=optuna.pruners.HyperbandPruner(),
            sampler=optuna.samplers.TPESampler(),
        )

        study.optimize(
            objective,
            n_trials=N_TRAILS,
            n_jobs=-1,
            show_progress_bar=True,
            catch=(ValueError,),
        )

        self.optimized_hyperparameters = study.best_params

        self.model = MaskablePPO(
            MaskableActorCriticPolicy,
            self.env,
            **self.optimized_hyperparameters,
            verbose=0,
            tensorboard_log=f"./tensorboard/",
            device=self.device,
        )

    def export_hyperparameters(self, filename: str):
        """
        Export optimized learned_hyperparameters to a YAML file.
        """
        with open(filename, "w") as file:
            yaml.dump(self.optimized_hyperparameters, file)

# %% ../nbs/10_player.ipynb 11
maskable_random_agent = MaskableRandomAgent(render_mode="human", env_config=ENV_CONFIG)

evaluation_data_per_agent[maskable_random_agent.name] = maskable_random_agent.evaluate()

# %% ../nbs/10_player.ipynb 13
a2c_agent = A2CAgent(render_mode="human", env_config=ENV_CONFIG)

a2c_agent.train()

if not QUICK_MODE:
    a2c_agent.save_model(f"{a2c_agent.name}.model")

evaluation_data_per_agent[a2c_agent.name] = a2c_agent.evaluate()

# %% ../nbs/10_player.ipynb 15
maskable_ppo_agent = MaskablePPOAgent(render_mode="human", env_config=ENV_CONFIG)

maskable_ppo_agent.train()

if not QUICK_MODE:
    maskable_ppo_agent.save_model(f"{maskable_ppo_agent.name}.model")

evaluation_data_per_agent[maskable_ppo_agent.name] = maskable_ppo_agent.evaluate()

# %% ../nbs/10_player.ipynb 17
optimized_maskable_ppo_agent = MaskablePPOAgent(
    render_mode="human", env_config=ENV_CONFIG, name="OptimizedMaskablePPOAgent"
)
optimized_maskable_ppo_agent.optimize()

if not QUICK_MODE:
    optimized_maskable_ppo_agent.export_hyperparameters(
        f"{optimized_maskable_ppo_agent.name}.yaml"
    )

optimized_maskable_ppo_agent.train()

if not QUICK_MODE:
    optimized_maskable_ppo_agent.save_model(
        f"{optimized_maskable_ppo_agent.name}.model"
    )

evaluation_data_per_agent[optimized_maskable_ppo_agent.name] = (
    optimized_maskable_ppo_agent.evaluate()
)

# %% ../nbs/10_player.ipynb 19
def is_action_safe(self, action: int) -> bool:
    charge_amount = self._charge_amount(action)
    target_state_of_charge = self._current_state_of_charge + charge_amount
    low, high = self._battery_safe_range
    return high > target_state_of_charge > low


def expert_knowledge_action_masks(self) -> np.ndarray:
    mask = np.array(
        [
            self._is_action_valid(action) and self.is_action_safe(action)
            for action in range(self.action_space.n)
        ],
        dtype=bool,
    )
    if not np.any(mask):
        mask[len(mask) // 2] = True
    return mask

# %% ../nbs/10_player.ipynb 20
# Dynamically overriding action_masks to ElectricityMarketEnv
setattr(ElectricityMarketEnv, "action_masks", expert_knowledge_action_masks)
# Dynamically overriding injection is_action_safe to ElectricityMarketEnv
setattr(ElectricityMarketEnv, "is_action_safe", is_action_safe)

# %% ../nbs/10_player.ipynb 22
expert_maskable_random_agent = MaskableRandomAgent(
    render_mode="human", env_config=ENV_CONFIG, name="ExpertMaskableRandomAgent"
)

evaluation_data_per_agent[expert_maskable_random_agent.name] = (
    expert_maskable_random_agent.evaluate()
)

# %% ../nbs/10_player.ipynb 24
expert_maskable_ppo_agent = MaskablePPOAgent(
    render_mode="human", env_config=ENV_CONFIG, name="ExpertMaskablePPOAgent"
)

expert_maskable_ppo_agent.train()


if not QUICK_MODE:
    expert_maskable_ppo_agent.save_model(f"{expert_maskable_ppo_agent.name}.model")

evaluation_data_per_agent[expert_maskable_ppo_agent.name] = (
    expert_maskable_ppo_agent.evaluate()
)

# %% ../nbs/10_player.ipynb 26
optimized_expert_maskable_ppo_agent = MaskablePPOAgent(
    render_mode="human", env_config=ENV_CONFIG, name="OptimizedExpertMaskablePPOAgent"
)
optimized_expert_maskable_ppo_agent.optimize()

if not QUICK_MODE:
    optimized_expert_maskable_ppo_agent.export_hyperparameters(
        f"{optimized_expert_maskable_ppo_agent.name}.yaml"
    )

optimized_expert_maskable_ppo_agent.train()

if not QUICK_MODE:
    optimized_expert_maskable_ppo_agent.save_model(
        f"{optimized_expert_maskable_ppo_agent.name}.model"
    )

evaluation_data_per_agent[optimized_expert_maskable_ppo_agent.name] = (
    optimized_expert_maskable_ppo_agent.evaluate()
)
