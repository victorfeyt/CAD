"""Example of Python tools for one persistent circuit-sizing experiment.

Copy this file and mcp_server.py to your CAD project root.
"""

import os
from copy import deepcopy
from datetime import datetime
from numbers import Real
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import subprocess

os.environ.setdefault("MPLBACKEND", "Agg")
from circuit_env import CircuitEnv
from td3 import ReplayBuffer, TD3


SPEC_UNITS = {
    "area": "m^2", "current": "A", "gain": "V/V", "noise": "V RMS",
    "phm": "deg", "slewRate": "V/us", "ugbw": "Hz",
}
MAX_STEPS_PER_CALL = 1000


def to_builtin(value):
    """Convert NumPy values to JSON-compatible Python values."""
    if isinstance(value, np.ndarray):
        return to_builtin(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    return value


def check_count(value, name, maximum):
    """Reject booleans, non-integers, and out-of-range requests."""
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}.")


class SizingExperiment:
    """One agent, replay buffer, and episode shared by successive tool calls.

    State lives in this object until the Python process exits. Use one experiment
    per process: the existing TD3 code uses NumPy/PyTorch global random generators.
    """

    def __init__(self, seed=123456, batch_size=100, replay_size=100_000):
        check_count(replay_size, "replay_size", 1_000_000)
        check_count(batch_size, "batch_size", replay_size)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("seed must be an integer from 0 to 2**32 - 1.")
        np.random.seed(seed)
        torch.manual_seed(seed)
        self.seed = seed
        self.batch_size = batch_size
        self.run_id = "mcp_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        self.env = CircuitEnv(run_id=self.run_id, success_threshold=0.0)
        # Direct design evaluations must not change the ongoing RL episode.
        self.evaluation_env = CircuitEnv(run_id=self.run_id + "_evaluate",
                                         success_threshold=0.0)
        self.env.action_space.seed(seed)
        Path(self.env.simulation_engine.output_files_folder).mkdir(parents=True, exist_ok=True)
        Path("solutions").mkdir(exist_ok=True)

        args = SimpleNamespace(gamma=0.99, tau=0.005, noise_sigma=0.1,
                               actor_update_interval=2, pi_lr=3e-4, q_lr=3e-4,
                               hidden_size=256, cuda=False)
        self.agent = TD3(self.env.observation_space.shape[0], self.env.action_space, args)
        self.replay = ReplayBuffer(self.env.observation_space.shape[0],
                                   self.env.action_space.shape[0], max_size=replay_size)
        self.observation = None  # None means the next RL step needs a reset.
        self.warmup_steps = 0
        self.training_steps = 0
        self.updates = 0
        self.simulator_calls = 0  # Attempts, including resets and failed calls.
        self.candidates = {}  # Parameter tuple -> latest measured result.

    def simulate(self, parameters: dict[str, float]) -> dict:
        """Evaluate one complete physical-parameter dictionary on the YAML grid.

        Return parameters, specs, normalized_specs, reward, constraint satisfaction,
        source, and spec_units. Record the candidate, without changing RL state,
        replay, or weights. Validation failures do not invoke the simulator.
        """
        parameters = self._validate_parameters(parameters) # validate parameters first before sim
        self.simulator_calls += 1
        try:
            specs = self.evaluation_env.simulate(parameters) # simulate the parameters
        except (IndexError, OSError) as error: 
            raise RuntimeError(f"Simulator failed: {error}") from error 
        return self._record(self.evaluation_env, parameters, specs, source="simulate")

    def warmup(self, n_steps: int) -> dict:
        """Append exactly n_steps random transitions, without updating weights.

        Continue the current episode. Return cumulative status plus steps_completed,
        experiences_added, simulator_calls_used, and updates_performed for this call.
        n_steps must be 1..1000. Reset simulations count as calls, not transitions.
        """
        return self._run_steps(n_steps, training=False)

    def train(self, n_steps: int) -> dict:
        """Collect exactly n_steps policy transitions and perform TD3 updates.

        Require at least batch_size experiences before starting. Reuse the same
        agent, replay, and unfinished episode. One learning update per new
        transition; the agent controls delayed actor updates. Return the same
        status and per-call counts as warmup. n_steps must be 1..1000.
        """
        return self._run_steps(n_steps, training=True)

    def get_status(self, k: int = 5) -> dict:
        """Return progress and the top k distinct measured designs (k=1..20).

        Rank by reward, highest first; a high reward does not imply feasibility.
        Include reset and standalone evaluations in candidate history. This call
        performs no simulations, sampling, or learning, and returns detached data.
        """
        check_count(k, "k", 20)
        best_candidates = sorted(self.candidates.values(),
                                 key=lambda c: c["reward"], reverse=True)[:k] # compare designs by their reward
        return {
        "run_id": self.run_id,
        "warmup_steps": self.warmup_steps,
        "training_steps": self.training_steps,
        "updates": self.updates,
        "simulator_calls": self.simulator_calls,
        "replay_size": self.replay.size,
        "batch_size": self.batch_size,
        "episode_in_progress": self.observation is not None,
        "candidates_recorded": len(self.candidates),
        "best_candidates": deepcopy(best_candidates[:k]),
    }

    def _validate_parameters(self, parameters):
        """Require every YAML parameter, finite numbers, and valid grid values.

        Use the same np.arange(min, max, step) grids as phase one. Canonicalize
        floating-point roundoff only; reject off-grid values rather than clipping.
        """

        if not isinstance(parameters, dict) or set(parameters) != set(self.env.dict_params):
            raise ValueError("parameters must contain exactly the YAML parameter names.")
        for name, value in parameters.items(): # check that all values are finite numbers
            if not isinstance(value, Real) or not np.isfinite(value) or isinstance(value, bool):
                raise ValueError(f"Parameter {name} must be a finite number.")
        param = {}
        for name, (min_val, max_val, step) in self.env.dict_params.items(): # through YAML parameters
            value = parameters[name] # which parameter
            grid = np.arange(min_val, max_val, step) # create grid of valid values
            idx = int(np.argmin(np.abs(grid - value))) # find the index of the closest grid value
            if abs(grid[idx]-value) > step * 1e-6: # check if the closest grid value is within tolerance
                raise ValueError(f"Parameter {name}={value} is not on the valid grid.")

            param[name] = grid[idx].item() # store the closest grid value in param
        return param

    def _record(self, env, parameters, specs, source):
        """Validate and save one candidate using the environment's scoring methods.

        Return a JSON-compatible candidate. Repeated parameters replace their
        previous measurement; failed or non-finite results must not enter history.
        """
        parameters = self._validate_parameters(parameters) # validated parameters
        if not np.all(np.isfinite(list(specs.values()))): # check if specs are valid
            raise ValueError("Specs must be finite numbers.")
        normalized_specs = env.normalize_specs(specs) # normalize specs
        reward, hard_satisfied = env.reward_computation(normalized_specs) # compute reward and hard constraints
        candidate = to_builtin({
            "parameters": parameters,
            "specs": specs,
            "normalized_specs": normalized_specs,
            "reward": reward,
            "hard_constraints_satisfied": hard_satisfied,
            "source": source,
            "spec_units": SPEC_UNITS,
        })
        self.candidates[tuple(parameters.values())] = candidate # store candidate in candidates dictionary
        return deepcopy(candidate) # return a deep copy of the candidate
    
    def _run_steps(self, n_steps, training):
        """Run a bounded batch, preserving episode state and reporting partial failures.

        Return get_status() plus per-call counts. Store full replay transitions;
        failed evaluations must not enter replay. Keep already completed work if
        a later step fails, and tell the caller to inspect get_status() before retrying.
        """
        check_count(n_steps, "n_steps", MAX_STEPS_PER_CALL)
        if training and self.replay.size < self.batch_size:
            raise ValueError(f"train needs at least {self.batch_size} experiences, "
                            f"the buffer has {self.replay.size}. Run warmup first.")

        source = "train" if training else "warmup"
        counts = {"steps_completed": 0, "experiences_added": 0,
                "simulator_calls_used": 0, "updates_performed": 0}
        try:
            while counts["steps_completed"] < n_steps:
                # Start a new episode only if the previous one finished
                if self.observation is None:
                    self.simulator_calls += 1
                    counts["simulator_calls_used"] += 1
                    observation = self.env.reset(seed=self.seed + 1 if self.env.env_steps == 0 else None)
                    self._record(self.env, self.env.param_values, self.env.real_specs, "reset")
                    self.observation = observation

                if training:
                    action = self.agent.select_action(self.observation)
                else:
                    action = self.env.action_space.sample()

                self.simulator_calls += 1
                counts["simulator_calls_used"] += 1
                next_observation, reward, done, _ = self.env.step(action)
                try:
                    self._record(self.env, self.env.param_values, self.env.real_specs, source)
                except ValueError:
                    if done:
                        self.observation = None
                    raise

                self.replay.push(self.observation, action, reward, next_observation, done)
                self.observation = None if done else next_observation
                counts["steps_completed"] += 1
                counts["experiences_added"] += 1

                if training:
                    batch = self.replay.sample(self.batch_size)
                    self.agent.update_parameters(batch, self.updates)
                    self.updates += 1
                    self.training_steps += 1
                    counts["updates_performed"] += 1
                else:
                    self.warmup_steps += 1

                if self.simulator_calls % 100 == 0:
                    subprocess.run(["./clean.sh"], stdout=subprocess.DEVNULL)
        except (RuntimeError, ValueError, IndexError, OSError) as error:
            raise RuntimeError(f"Stopped after {counts['steps_completed']} of {n_steps} steps: {error} "
                            "Completed work is kept; inspect get_status() before retrying.") from error

        return {**self.get_status(), **counts}

