import gymnasium as gym
from gymnasium.spaces import Box
import numpy as np
import os
import yaml
import math
from ngspice_interface import DUT as DUT_NGSpice
from utils.plotting import plotLearning, plot_running_maximum
from utils.saving import save_solutions_csv

class CircuitEnv(gym.Env):
    PER_LOW, PER_HIGH = -np.inf, +np.inf
    
    def __init__(self, config=None, circuit_name='TwoStage', run_id='rllib_baseline',
                 success_threshold=0.0, simulator='ngspice'):
        self.run_id = run_id
        self.max_steps_per_episode = 10
        self.env_steps = 0
        self.episode_steps = 0
        self.success_threshold = success_threshold
        self.circuit_name = circuit_name

        project_path = os.getcwd()
        yaml_directory = os.path.join(project_path, f"{simulator}_interface", 'files', 'yaml_files')
        circuit_yaml_path = os.path.join(yaml_directory, f'{circuit_name}.yaml')
        with open(circuit_yaml_path, 'r') as f:
            yaml_data = yaml.load(f, Loader=yaml.Loader)
        
        self.dict_params = yaml_data['params']
        self.dict_targets = yaml_data['targets']

        self.hard_constraints = yaml_data['hard_constraints']
        self.optimization_targets = yaml_data['optimization_targets']

        # specs where a value below the goal is good (all others: higher is better)
        self.lower_is_better = set(self.optimization_targets) | {'noise'}

        # number of input action components
        self.n_actions = len(self.dict_params)

        # number of output observation components
        self.obs_dim = len(self.dict_targets)

        self.param_ranges = {}
        for name, value in self.dict_params.items():
           self.param_ranges[name] = {'min': value[0], 'max': value[1], 'step': value[2]}
        
        self.simulation_engine = DUT_NGSpice(circuit_yaml_path)

        print(f"\n Initialized {circuit_name} with simulator {simulator} \n")

        # Action space & Observation space
        act_high = np.array([1 for _ in range(self.n_actions)])
        act_low = np.array([-1 for _ in range(self.n_actions)])
        self.action_space = Box(low=act_low, high=act_high)
        obs_high = np.array([CircuitEnv.PER_HIGH]*self.obs_dim, dtype=np.float32)
        obs_low = np.array([CircuitEnv.PER_LOW]*self.obs_dim, dtype=np.float32)
        self.observation_space = Box(low=obs_low, high=obs_high)

        # spec reward weights
        self.spec_weights = yaml_data['spec_weights']

        self.reward_history = []
        self.score_history = []
        self.score = 0.0

        self.counter = 0
        self.pvt_corner = {'process': 'TT', 'voltage': 1.2, 'temp': 27}
    
    def action_refine(self, action):
        """
        Implement a function that converts normalized actions of range [-1, 1] to actual parameter values.
        """
        action = np.clip(np.asarray(action, dtype=np.float64).flatten(), -1, 1)

        params = {}
        for i, (name, value) in enumerate(self.dict_params.items()):
            min_val, max_val, step = value
            grid = np.arange(min_val, max_val, step)
            idx = int((action[i] + 1) / 2 * (len(grid) - 1))
            params[name] = grid[idx]

        return params

    def simulate(self, params):
        """
        Create/Simulate netlist with the given parameters and return the measured metrics.
        Args:
            params (dict): A dictionary containing the parameters for the simulation.

        Returns:
            dict: A dictionary containing the measured metrics from the simulation.
        """
        params = {name: float(value) for name, value in params.items()}

        # Create a new netlist with the given parameters
        netlist_path = self.simulation_engine.create_new_netlist(
            parameters=params,
            process=self.pvt_corner['process'],
            temp_pvt=self.pvt_corner['temp'],
            vdd=self.pvt_corner['voltage']
            )

        # Run the simulation check for errors
        info = self.simulation_engine.simulate(netlist_path)

        # Return the measured metrics from the simulation
        # simulate() returns 0 on success, 1 if ngspice failed
        if info == 1:
            raise RuntimeError(f"ngspice simulation failed for {netlist_path}")

        specs = self.simulation_engine.measure_metrics()
        return {name: float(value) for name, value in specs.items()}

    def normalize_specs(self, spec_dict):
        """
        Normalize the specifications in `spec_dict` based on target specifications.

        This function normalizes the values in `spec_dict` by comparing them to the
        target specifications stored in `self.dict_targets`. The normalization is 
        performed using the formula:
            normalized_value = (spec_value - goal_value) / (spec_value + goal_value) 
        
        Args:
            spec_dict (dict): A dictionary containing the specifications to be normalized.
                              The keys should match those in `self.dict_targets`.
        
        Returns:
            dict: A dictionary containing the normalized specifications, with the same keys
                  as `spec_dict`.
        """
        norm_specs = {}
        for name, goal in self.dict_targets.items():
            # phm is the only spec that can go negative. The formula breaks there: it blows
            # up near spec = -goal and turns positive below it, so an unstable circuit would
            # look like it beats the target. Treating negative specs as 0 gives -1 instead.
            spec = max(spec_dict[name], 0.0)
            norm_specs[name] = (spec - goal) / (spec + goal)
        return norm_specs
    
    def evaluate(self, action):
        self.param_values = self.action_refine(action)
        try:
            self.real_specs = self.simulate(self.param_values)
            if not np.all(np.isfinite(list(self.real_specs.values()))):
                raise ValueError(f"non-finite specs: {self.real_specs}")
            self.cur_norm_specs = self.normalize_specs(self.real_specs)
        except (RuntimeError, ValueError, IndexError, OSError) as error:
            # A failed design must not stop training: give it the worst possible norm specs
            # so the agent learns to avoid it.
            print(f"[env step {self.env_steps}] simulation failed: {error}")
            self.real_specs = {name: float('nan') for name in self.dict_targets}
            self.cur_norm_specs = {name: 1.0 if name in self.lower_is_better else -1.0
                                   for name in self.dict_targets}
    
    def reset(self, *, seed=None, options=None):
        """
        Reset the environment to an initial state and return the initial observation.

        Parameters:
            No mandatory input parameters (leave the input signature as is).
            seed (int, optional): A seed for the random number generator to ensure reproducibility.
            options (dict, optional): Additional options for the reset process.

        Returns:
            np.ndarray: The initial observation of the environment, which is the normalized current specifications.

        This method performs the following steps:
        1. Initializes the episode steps counter to zero.
        2. Generates a random action within the range [-1, 1] for each action parameter.
        3. Evaluates the environment with the generated random action.
        4. Resets the episode score to zero.
        5. Constructs the initial observation by returning the normalized current specifications.

        Note:
        - The observation is returned as a NumPy array of type float32.
        """
        super().reset(seed=seed)
        self.episode_steps = 0
        random_action = self.np_random.uniform(-1, 1, [self.n_actions])
        self.evaluate(random_action)
        self.score = 0.0
        return np.array(list(self.cur_norm_specs.values()), dtype=np.float32)

    def step(self, action):
        """
        Perform a single step in the environment using the given action.

        This function should:
        1. Evaluate the given action.
        2. Compute the reward and check if the hard constraints are satisfied.
        3. Update the current observation.
        4. Append the reward to the reward history and update the score.
        5. Create output directories if they do not exist.
        6. If the goal state is reached, plot the running maximum reward.
        7. Increment the environment and episode step counters.
        8. Check if the maximum steps per episode have been reached, setting the done flag if true.
        9. Every 10 steps, update the score history, also plot the learning curve, and reset the score.
        10. Return the current observation, reward, done flag, and additional information.

        Args:
            action: The action to be taken in the environment. An array of values between -1 and 1.

        Returns:
            tuple: A tuple containing:
            - ob (np.ndarray): The current observation of the environment.
            - reward (float): The reward obtained from taking the action.
            - done (bool): A flag indicating whether the episode has ended.
            - info (dict): Additional information, including whether the goal state was reached.
        """
        self.evaluate(action)
        reward, hard_satisfied = self.reward_computation(self.cur_norm_specs)
        ob = np.array(list(self.cur_norm_specs.values()), dtype=np.float32)

        self.reward_history.append(reward)
        self.score += reward

        fig_dir = os.path.join('.', 'output_figs', str(self.run_id))
        os.makedirs(fig_dir, exist_ok=True)
        os.makedirs(os.path.join('.', 'solutions'), exist_ok=True)

        if hard_satisfied:
            # .item(): store plain Python numbers, not np.int64(...) reprs, in the CSV
            params = {name: value.item() for name, value in self.param_values.items()}
            save_solutions_csv(self.run_id, self.env_steps, params, self.real_specs, reward)
            plot_running_maximum(self.reward_history, self.run_id)

        self.env_steps += 1
        self.episode_steps += 1

        done = self.episode_steps >= self.max_steps_per_episode

        if self.env_steps % 10 == 0:
            self.score_history.append(self.score)
            plotLearning(self.score_history, self.run_id)
            self.score = 0.0

        info = {'goal_reached': hard_satisfied}
        return ob, reward, done, info
    
    def reward_computation(self, norm_specs):
        """
        Compute the reward based on normalized specifications and hard constraints.

        Args:
            norm_specs (dict): A dictionary containing normalized specifications.

        Returns:
            tuple: A tuple containing:
            - reward (float): The computed reward value.
            - hard_satisfied (bool): A boolean indicating whether the hard constraints are satisfied.

        The function performs the following steps:
        1. Initialize the reward to 0.0 and hard_satisfied to False.
        2. Iterate over the hard constraints and adjust the reward based on the specifications.
        3. Check if all hard constraints are satisfied or the total reward passes the success threshold of 0.
            - If so, set hard_satisfied to True, add a bonus reward (+0.3), and adjust the reward based on optimization targets.
            - If not, add weighted reward components of the optimization targets.
        4. Return the computed reward and the hard_satisfied flag.
        """
        reward = 0.0
        hard_satisfied = False
        
        def margin(spec):
            # > 0 means the spec beats its target, < 0 means it misses it
            return -norm_specs[spec] if spec in self.lower_is_better else norm_specs[spec]

        for spec in self.hard_constraints:
            reward += self.spec_weights[spec] * min(margin(spec), 0.0)

        if reward >= self.success_threshold:
            hard_satisfied = True
            reward += 0.3
            for spec in self.optimization_targets:
                reward += self.spec_weights[spec] * margin(spec)
        else:
            # Hard constraints still missed: the optimization targets count unclipped
            # but at only 5% weight, so shrinking area/current can't buy back a missed
            # constraint (this is the rule the references.csv rewards follow).
            for spec in self.optimization_targets:
                reward += 0.05 * self.spec_weights[spec] * margin(spec)

        return reward, hard_satisfied

if __name__ == '__main__':
    env = CircuitEnv(
        circuit_name='TwoStage', 
        run_id=0, 
        simulator='ngspice', 
        success_threshold=0.0
        )
    print(env.action_space)
    print(env.observation_space)

    ob = env.reset()
    print("Initial observation: ", ob)
    print("Initial parameters: ", env.param_values)
    print("Initial specs: ", env.real_specs)

    action = np.random.uniform(-1, 1, [env.n_actions])
    ob, reward, done, info = env.step(action)
    print("Next parameters: ", env.param_values)
    print("Next observation: ", ob)
    print("Next specs: ", env.real_specs)
    print("Reward: ", reward)
    print("Done: ", done)
