"""This module contains useful datastructures for RL evaluation."""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/05_utils.ipynb.

# %% auto 0
__all__ = ['TrainingData', 'EvaluationData']

# %% ../nbs/05_utils.ipynb 3
from dataclasses import dataclass

import numpy as np

# %% ../nbs/05_utils.ipynb 4
@dataclass
class TrainingData:
    steps: list[int]
    episodes: list[int]
    rewards: list[float]


@dataclass
class EvaluationData:
    episodes: list[int]
    rewards: list[float]
