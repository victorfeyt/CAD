import argparse
import os
import shutil
import torch
import numpy as np
from td3 import TD3, ReplayBuffer
from circuit_env import CircuitEnv
from utils.plotting import solutions2pareto
from datetime import datetime

def readParser():
    parser = argparse.ArgumentParser(description='TD3-based RL for Circuit Sizing')

    parser.add_argument('--seed', type=int, default=123456, metavar='N',
                        help='random seed')

    parser.add_argument('--noise_sigma', type=float, default=0.1,
                        help='fixed noise sigma added to the deterministic action')

    parser.add_argument('--gamma', type=float, default=0.9, metavar='G',
                        help='discount factor for reward')
    
    parser.add_argument('--tau', type=float, default=0.005, metavar='G',
                        help='target smoothing coefficient(τ)')
    
    parser.add_argument('--target_update_interval', type=int, default=1, metavar='N',
                        help='Value target update per no. of updates per step')
    
    parser.add_argument('--actor_update_interval', type=int, default=1, metavar='N',
                        help='Actor target update per no. of updates per step')
    
    parser.add_argument('--hidden_size', type=int, default=256, metavar='N',
                        help='hidden size (default: 256)')
    
    parser.add_argument('--batch_size', type=int, default=256, metavar='N',
                        help='hidden size')
    
    parser.add_argument('--w', type=int, default=1024, metavar='N',
                        help='number of warmup steps')
    
    parser.add_argument('--T', type=int, default=5000, metavar='N',
                        help='total training steps')
    
    parser.add_argument('--pi_lr', type=float, default=0.0001, metavar='G',
                        help='learning rate')
    
    parser.add_argument('--q_lr', type=float, default=0.0003, metavar='G',
                        help='learning rate')

    parser.add_argument('--replay_size', type=int, default=1000000, metavar='N',
                        help='size of replay buffer')

    parser.add_argument('--cuda', default=False, action="store_true",
                        help='run on CUDA')
    
    parser.add_argument('--run_id', type=str, default=datetime.now().strftime('%Y-%m-%d--%H-%M-%S'), metavar='N',
                        help='run identifier')
    
    return parser.parse_args()


def train(args, env, agent, env_pool):
    total_steps = warmup_exploration(args, env, env_pool, agent)
    while total_steps < args.T:
        obs = env.reset()
        done = False
        while not done:
            action = agent.select_action(obs)
            next_state, reward, done, info = env.step(action)
            env_pool.push(obs, action, reward, next_state, done)
            obs = next_state
            train_policy(args, env_pool, agent, total_steps)
            total_steps += 1
            # clean up the no_backup folder every 100 steps
            if total_steps % 100 == 0:
                clean_no_backup()


def clean_no_backup(target_dir='no_backup'):
    """Python version of clean.sh (os.system('./clean.sh') fails on Windows' cmd.exe)."""
    os.makedirs(target_dir, exist_ok=True)
    for entry in os.listdir(target_dir):
        path = os.path.join(target_dir, entry)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass  # e.g. a file still locked by ngspice; it gets removed next time
    os.makedirs(os.path.join(target_dir, 'output_files'), exist_ok=True)
    os.makedirs(os.path.join(target_dir, 'output_netlists'), exist_ok=True)


def warmup_exploration(args, env, env_pool, agent):
    step_counter = 0
    while step_counter < args.w:
        obs = env.reset()
        done = False
        while not done:
            action = env.action_space.sample()
            next_state, reward, done, info = env.step(action)
            env_pool.push(obs, action, reward, next_state, done)
            obs = next_state
            step_counter += 1
    return step_counter


def train_policy(args, env_pool, agent, total_steps):
    state, action, next_state, reward, not_done = env_pool.sample(args.batch_size)
    batch = (state, action, next_state, reward, not_done)
    agent.update_parameters(memory_batch=batch, update=total_steps)


def set_seed(seed):
    """
    Seed the global RNGs so that the same seed and hyperparameters reproduce a run exactly.
    The env's own RNGs (initial designs, warm-up actions) are seeded by CircuitEnv(seed=...).
    Python's `random` stays unseeded on purpose: it only names ngspice's temp files, and
    seeded names could collide between parallel runs with the same seed.
    """
    np.random.seed(seed)     # exploration noise (TD3.select_action), replay buffer sampling
    torch.manual_seed(seed)  # network initialization, target policy noise (CPU and all GPUs)
    # agent.py runs on the GPU whenever one is available: make its kernels deterministic too
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    torch.use_deterministic_algorithms(True)


def main(args=None):
    if args is None:
        args = readParser()
    # Set random seeds: the global RNGs here, the env's own RNGs through its constructor
    set_seed(args.seed)
    # Initial environment
    env = CircuitEnv(run_id=args.run_id, seed=args.seed)
    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]
    # Intial agent
    agent = TD3(state_dim, env.action_space, args)
    # Initial pool for env
    env_pool = ReplayBuffer(state_dim, action_dim, max_size=args.replay_size)
    # Training
    train(args, env, agent, env_pool)
    # Pareto front (area vs. current) of all solutions that satisfied the hard constraints
    solutions_csv = f'./solutions/{args.run_id}.csv'
    if os.path.isfile(solutions_csv):
        solutions2pareto(solutions_csv, args.run_id, show_all=True)
    else:
        print(f'No solutions file at {solutions_csv}; skipping Pareto plot.')


if __name__ == "__main__":
    main()