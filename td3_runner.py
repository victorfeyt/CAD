import argparse
import os
import torch
import numpy as np
from td3 import TD3, ReplayBuffer
from circuit_env import CircuitEnv
from datetime import datetime

def readParser():
    parser = argparse.ArgumentParser(description='TD3-based RL for Circuit Sizing')

    parser.add_argument('--seed', type=int, default=123456, metavar='N',
                        help='random seed (default: 123456)')

    parser.add_argument('--noise_sigma', type=float, default="???",
                        help='fixed noise sigma added to the deterministic action')

    parser.add_argument('--gamma', type=float, default=0.99, metavar='G',
                        help='discount factor for reward (default: 0.99)')
    
    parser.add_argument('--tau', type=float, default=0.005, metavar='G',
                        help='target smoothing coefficient(τ) (default: 0.005)')
    
    parser.add_argument('--target_update_interval', type=int, default=1, metavar='N',
                        help='Value target update per no. of updates per step (default: 1)')
    
    parser.add_argument('--actor_update_interval', type=int, default=2, metavar='N',
                        help='Actor target update per no. of updates per step (default: 2)')
    
    parser.add_argument('--hidden_size', type=int, default=256, metavar='N',
                        help='hidden size (default: 256)')
    
    parser.add_argument('--batch_size', type=int, default="???", metavar='N',
                        help='hidden size')
    
    parser.add_argument('--w', type=int, default="???", metavar='N',
                        help='number of warmup steps')
    
    parser.add_argument('--T', type=int, default=10_000, metavar='N',
                        help='total training steps (default: 10_000)')
    
    parser.add_argument('--pi_lr', type=float, default="???", metavar='G',
                        help='learning rate')
    
    parser.add_argument('--q_lr', type=float, default="???", metavar='G',
                        help='learning rate')

    parser.add_argument('--replay_size', type=int, default=1000000, metavar='N',
                        help='size of replay buffer (default: 10000000)')

    parser.add_argument('--cuda', default=False, action="store_true",
                        help='run on CUDA (default: True)')
    
    parser.add_argument('--run_id', type=str, default=datetime.now().strftime('%Y-%m-%d--%H-%M-%S'), metavar='N',
                        help='run identifier (default: current time)')
    
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
                os.system('./clean.sh')



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
    state, action, reward, next_state, done = env_pool.sample(args.batch_size)
    batch = (state, action, reward, next_state, done)
    agent.update_parameters(memory=batch, update=total_steps)


def main(args=None):
    if args is None:
        args = readParser()
    # Set random seed
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    # Initial environment
    env = CircuitEnv(run_id=args.run_id)
    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]
    # Intial agent
    agent = TD3(state_dim, env.action_space, args)
    # Initial pool for env
    env_pool = ReplayBuffer(state_dim, action_dim, max_size=args.replay_size)
    # Training
    train(args, env, agent, env_pool)


if __name__ == "__main__":
    main()