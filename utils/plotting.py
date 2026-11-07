import os
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Dict
import pandas as pd
import matplotlib

def plotLearning(scores, run_id):
    filename = f'./output_figs/{run_id}/average_score.png'
    N = len(scores)
    # Calculate the running average of scores
    running_avg = np.zeros(N)
    for t in range(N):
        running_avg[t] = np.mean(scores[max(0, t-N):(t+1)])

    # change the font size
    plt.rcParams.update({'font.size': 18})
    plt.ylabel('Episode Scores')       
    plt.xlabel('# Episode')                     
    plt.plot(range(N), running_avg, label='Running Avg')
    plt.plot(range(N), scores, alpha=0.5, label='Scores')  # Optionally overlay the raw scores
    plt.legend()
    plt.grid('on')
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

def plot_running_maximum(data, run_id):
    file_name = f'./output_figs/{run_id}/max_reward.png'
    running_max = float('-inf')  # Initialize running maximum to negative infinity
    running_max_values = []

    for value in data:
        if value > running_max:
            running_max = value
        running_max_values.append(running_max)

    # change the font size
    plt.rcParams.update({'font.size': 18})
    plt.plot(running_max_values)

    # mark and label the final maximum at the first simulation that reached it
    best_idx = int(np.argmax(data))
    best_value = data[best_idx]
    ax = plt.gca()
    ax.plot(best_idx, best_value, 'o', markersize=10, color='C0', markeredgecolor='white', zorder=3)
    ax.annotate(f'Max reward: {best_value:.4f}\n(simulation {best_idx})',
                xy=(best_idx, best_value), xytext=(0.95, 0.45), textcoords='axes fraction',
                ha='right', va='center', multialignment='center', fontsize=16,
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='0.7'),
                arrowprops=dict(arrowstyle='->', color='0.3', lw=1.5))

    plt.xlabel('# Simulation')
    plt.ylabel('Maximum FoM Reached')
    # plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(file_name)
    plt.close()
    

def is_pareto_efficient(costs: np.ndarray) -> np.ndarray:
    is_efficient = np.ones(costs.shape[0], dtype=bool)
    for i, c in enumerate(costs):
        if is_efficient[i]:
            is_efficient[is_efficient] = np.any(costs[is_efficient] < c, axis=1)
            is_efficient[i] = True
    return is_efficient

def plot_pareto_front(solutions: List[Dict[str, float]], fname, show_all=False) -> None:
    current_scaled = [sol['current']*1e+6 for sol in solutions] # --> convert to μA
    area_scaled = [sol['area']*1e12 for sol in solutions] # --> convert to μm²

    combined_objectives = np.vstack((area_scaled, current_scaled)).T
    pareto_optimal_indices = is_pareto_efficient(combined_objectives)
    
    pareto_optimal_points = combined_objectives[pareto_optimal_indices]
    pareto_area = pareto_optimal_points[:, 0]
    pareto_current = pareto_optimal_points[:, 1]

    # change the font size
    plt.rcParams.update({'font.size': 18})

    fig, ax = plt.subplots(figsize=(8, 6))
    if show_all:
        ax.scatter(area_scaled, current_scaled, c='gray', alpha=0.4, s=60, label='Non-Pareto Solutions', zorder=1)
    ax.scatter(pareto_area, pareto_current, c='blue', s=100, edgecolors='white', label='Pareto Front', zorder=3)

    sorted_indices = np.argsort(pareto_area)
    ax.plot(pareto_area[sorted_indices], pareto_current[sorted_indices], 'b--', linewidth=2, zorder=2)
    ax.legend(fontsize=14)
    
    ax.set_xlabel('Active Area (μm²)', fontsize=18)
    ax.set_ylabel('Total Current (μA)', fontsize=18)

    # show grids for both x and y axis
    ax.grid(True, linestyle='--', alpha=0.7, which='both')

    
    plt.tight_layout()
    plt.savefig(fname, dpi=300, bbox_inches='tight')
    plt.close()


def solutions2pareto(csv_fname, run_id, show_all=False):
    plot_fname = f'./output_figs/{run_id}/pareto.png'
    df = pd.read_csv(csv_fname)
    solutions = df['Specs'].apply(eval).tolist()
    plot_pareto_front(solutions, plot_fname, show_all)


def compare_solutions(csv_a, csv_b, labels=None, out_dir='./output_figs/comparison', show_all=False):
    """Compare two runs from their solutions CSVs.

    Saves `max_reward.png` (running maximum reward vs. simulation step) and
    `pareto.png` (area/current Pareto fronts) in `out_dir`. The CSVs only hold
    designs that met the hard constraints, so both plots cover feasible designs only.
    Returns the paths of the two figures.
    """
    csvs = [csv_a, csv_b]
    labels = labels or [os.path.splitext(os.path.basename(f))[0] for f in csvs]
    colors = ['C0', 'C1']
    dfs = []
    for f in csvs:
        df = pd.read_csv(f).dropna(subset=['Simulation step', 'Reward']).sort_values('Simulation step')
        df['Specs'] = df['Specs'].apply(eval)
        dfs.append(df)

    os.makedirs(out_dir, exist_ok=True)
    plt.rcParams.update({'font.size': 18})

    # running maximum reward; the dot marks the first simulation that reached each run's maximum
    reward_fname = os.path.join(out_dir, 'max_reward.png')
    fig, ax = plt.subplots(figsize=(8, 6))
    for df, label, color in zip(dfs, labels, colors):
        best = df['Reward'].idxmax()
        best_step, best_reward = df.at[best, 'Simulation step'], df.at[best, 'Reward']
        ax.step(df['Simulation step'], df['Reward'].cummax(), where='post', color=color, linewidth=2,
                label=f'{label} (max {best_reward:.4f} @ sim {best_step})')
        ax.plot(best_step, best_reward, 'o', markersize=10, color=color, markeredgecolor='white', zorder=3)
    ax.set_xlabel('# Simulation')
    ax.set_ylabel('Maximum FoM Reached')
    ax.legend(fontsize=14)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(reward_fname, dpi=300, bbox_inches='tight')
    plt.close(fig)

    # Pareto fronts in area (μm²) vs. current (μA)
    pareto_fname = os.path.join(out_dir, 'pareto.png')
    fig, ax = plt.subplots(figsize=(8, 6))
    for df, label, color in zip(dfs, labels, colors):
        points = np.array([[s['area'] * 1e12, s['current'] * 1e6] for s in df['Specs']])
        front = points[is_pareto_efficient(points)]
        front = front[np.argsort(front[:, 0])]
        if show_all:
            ax.scatter(points[:, 0], points[:, 1], color=color, alpha=0.2, s=40, zorder=1)
        ax.plot(front[:, 0], front[:, 1], '--o', color=color, linewidth=2, markersize=9,
                markeredgecolor='white', label=f'{label} Pareto front', zorder=3)
    ax.set_xlabel('Active Area (μm²)')
    ax.set_ylabel('Total Current (μA)')
    ax.legend(fontsize=14)
    ax.grid(True, linestyle='--', alpha=0.7, which='both')
    fig.tight_layout()
    fig.savefig(pareto_fname, dpi=300, bbox_inches='tight')
    plt.close(fig)

    return reward_fname, pareto_fname