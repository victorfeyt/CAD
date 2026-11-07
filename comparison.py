"""Generate average_score.png, max_reward.png and pareto.png from a solutions CSV.

The CSV (written by utils/saving.py) only contains designs that satisfied the hard
constraints, so the curves are plotted against the simulation step of each such design.

It also compares the baseline with the most recently modified other CSV in the same
folder (or --compare), saving max_reward.png and pareto.png to
output_figs/comparison/<other>_vs_<run-id>.

Usage:
    python baseline_runner.py                      # solutions/baseline.csv -> output_figs/baseline
    python baseline_runner.py --csv solutions/x.csv --run-id x
    python baseline_runner.py --compare solutions/td3_run.csv
"""
import argparse
import os

import matplotlib
matplotlib.use('Agg')  # file output only, no GUI window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from utils.plotting import plot_pareto_front, compare_solutions

ROOT = os.path.dirname(os.path.abspath(__file__))


def latest_solutions_csv(solutions_dir, exclude):
    """Most recently modified CSV in `solutions_dir` other than `exclude`, or None."""
    exclude = os.path.abspath(exclude)
    csvs = [os.path.join(solutions_dir, f) for f in os.listdir(solutions_dir) if f.endswith('.csv')]
    return max((f for f in csvs if os.path.abspath(f) != exclude), key=os.path.getmtime, default=None)


def load_solutions(csv_path):
    df = pd.read_csv(csv_path)  # blank separator rows are skipped by default
    df = df.dropna(subset=['Simulation step', 'Reward'])
    df = df.sort_values('Simulation step').reset_index(drop=True)
    df['Specs'] = df['Specs'].apply(eval)
    return df


def plot_average_score(steps, rewards, fname):
    running_avg = np.cumsum(rewards) / np.arange(1, len(rewards) + 1)

    plt.rcParams.update({'font.size': 18})
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(steps, rewards, alpha=0.5, label='Reward')
    ax.plot(steps, running_avg, linewidth=2, label='Running Avg')
    ax.set_xlabel('# Simulation')
    ax.set_ylabel('Reward (feasible designs)')
    ax.legend()
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


def plot_max_reward(steps, rewards, fname):
    running_max = np.maximum.accumulate(rewards)

    plt.rcParams.update({'font.size': 18})
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.step(steps, running_max, where='post', linewidth=2)

    best_idx = int(np.argmax(rewards))  # first step at which the final maximum was reached
    best_step, best_reward = steps[best_idx], rewards[best_idx]
    ax.plot(best_step, best_reward, 'o', markersize=10, color='C0', markeredgecolor='white', zorder=3)
    ax.annotate(f'Max reward: {best_reward:.4f}\n(simulation {int(best_step)})',
                xy=(best_step, best_reward), xytext=(0.95, 0.45), textcoords='axes fraction',
                ha='right', va='center', multialignment='center', fontsize=16,
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='0.7'),
                arrowprops=dict(arrowstyle='->', color='0.3', lw=1.5))

    ax.set_xlabel('# Simulation')
    ax.set_ylabel('Maximum FoM Reached')
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(fname)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--csv', default=os.path.join(ROOT, 'solutions', 'baseline.csv'))
    parser.add_argument('--run-id', default='baseline')
    parser.add_argument('--compare', default=None,
                        help='solutions CSV to compare with (default: most recent other CSV next to --csv)')
    args = parser.parse_args()

    out_dir = os.path.join(ROOT, 'output_figs', args.run_id)
    os.makedirs(out_dir, exist_ok=True)

    df = load_solutions(args.csv)
    steps = df['Simulation step'].to_numpy()
    rewards = df['Reward'].to_numpy(dtype=float)

    plot_average_score(steps, rewards, os.path.join(out_dir, 'average_score.png'))
    plot_max_reward(steps, rewards, os.path.join(out_dir, 'max_reward.png'))
    plot_pareto_front(df['Specs'].tolist(), os.path.join(out_dir, 'pareto.png'), show_all=True)

    best = df.loc[rewards.argmax()]
    print(f'{len(df)} feasible designs from {args.csv}')
    print(f'Best reward {best["Reward"]:.4f} at simulation step {int(best["Simulation step"])}')
    print(f'Figures saved to {out_dir}')

    compare_csv = args.compare or latest_solutions_csv(os.path.dirname(os.path.abspath(args.csv)), args.csv)
    if compare_csv is None:
        print('No other solutions CSV found to compare with')
        return
    compare_id = os.path.splitext(os.path.basename(compare_csv))[0]
    cmp_dir = os.path.join(ROOT, 'output_figs', 'comparison', f'{compare_id}_vs_{args.run_id}')
    compare_solutions(compare_csv, args.csv, labels=[compare_id, args.run_id], out_dir=cmp_dir, show_all=True)
    print(f'Comparison with {compare_csv} saved to {cmp_dir}')


if __name__ == '__main__':
    main()
