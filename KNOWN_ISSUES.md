# Known issues and lessons

Bugs found while getting the RL training running (milestone 3), and what to watch for.
Last updated: 2026-11-05.

**Most important to know:** results from before the fixes in section 1 are not valid.
This includes the `base` run in `output_figs/`. Do not use its curves in the report.

## 1. Fixed: environment and simulator

### 1.1 Unstable circuits counted as meeting the phase margin target
- **Where:** `normalize_specs` in `circuit_env.py`
- **Problem:** `(spec - goal) / (spec + goal)` assumes positive specs, but phase margin can be negative. The formula blows up near PM = -60° and turns positive below it.

| PM | Old value | Now |
|---|---|---|
| 64° | 0.03 | 0.03 |
| -59.7° | -399 | -1 |
| -70° | +13 | -1 |
| -180° (no UGBW) | +2 | -1 |

- **Effect:** PM below -60° passed the constraint, so the agent could be rewarded for unstable designs.
- **Fix:** `spec = max(spec, 0.0)` before normalizing. Positive specs are unchanged, so the TA references still match.
- **Lesson:** clipping the result to [-1, 1] would not have fixed this, because +13 would become +1, which still passes. Check a formula at the edges of its input range, not only at typical values.

### 1.2 One bad design could hang training forever
- **Where:** `simulate` in `ngspice_interface/ngspice_wrapper.py`
- **Problem:** the ngspice call had no timeout. One simulation ran for minutes at 95% CPU and blocked the run. That design had `res = 0` and `cap = 0.1 pF`, both at their minimum. The simulation before it wrote 18.7 MB of transient data instead of the usual 78 KB, which suggests ngspice's time step collapsed. The exact cause is not proven.
- **Fix:** `SIM_TIMEOUT = 10` seconds. After that, ngspice is killed and the simulation counts as failed.
- **Trade-off:** a slow but valid design now also counts as failed. Normal simulations take well under a second.
- **Lesson:** a process can look alive and still make no progress. Any external call in a long loop needs a timeout.

### 1.3 One failed simulation stopped the whole run
- **Where:** `evaluate` in `circuit_env.py`
- **Problem:** `simulate()` raises `RuntimeError` on failure, and nothing caught it. The runner never saves the agent, so the trained networks would be lost.
- **Fix:** `evaluate` catches the error and gives the design the worst normalized value on every spec, which is a reward of -5.1 (the lowest possible). It prints `[env step N] simulation failed: ...`.
- **Lesson:** in RL, a failed design is useful feedback. Treat it as a bad result, not as a crash.

### 1.4 NaN or infinite specs could corrupt the networks
- **Where:** `evaluate` in `circuit_env.py`
- **Problem:** ngspice can exit normally and still produce unusable results. One NaN reward in the replay buffer can spread through the networks.
- **Fix:** non-finite specs are now handled as a failed simulation (see 1.3).

## 2. Fixed: TD3 agent and runner

| Bug | Where | Fix | Lesson |
|---|---|---|---|
| Soft update of the targets ran on every call | `update_parameters` in `td3/agent.py` | Moved inside `if total_it % policy_freq == 0` | Wrong indentation in Python can change the algorithm without any error |
| `.numpy().detach()` crashes | `select_action` in `td3/agent.py` | Removed `.detach()` | `detach` is a tensor method, so it must come before `.numpy()` |
| Mixed tabs and spaces | `td3/agent.py` | Converted the file to spaces | Python 3 raises `TabError` when a block mixes them |
| `update_parameters(memory=batch)` | `td3_runner.py` | Changed to `memory_batch=batch` | The keyword must match the parameter name |

## 3. Traps in the code to keep in mind

- **Batch order:** the replay buffer returns `state, action, next_state, reward, not_done`. `train_policy` in `td3_runner.py` names them in a different order. It only works because they are repacked in the same order straight away. Swapping names when unpacking gives no error, just a critic that learns garbage.
- **`action_refine`:** the mapping (`np.arange` with max excluded, truncated index) was reverse-engineered from `references.csv`, where it matches 100/100 values. It is not confirmed by the TAs. A consequence is that the maximum of each parameter can never be reached.
- **`done`:** it marks the 10-step time limit, not a true end state. The template still stops bootstrapping there. Worth one sentence in the report.

## 4. Still open

- **Reward when the constraints are met:** the `+0.3` branch is not tested against the references, because none of the 5 designs reaches it. The `0.05` factor in the other branch was fitted to those 5 designs. Ask the TAs, or check one case by hand.
- **The -420 spike in the `base` run:** PM close to -60° fits the numbers, but this was not confirmed from logged specs. Check that it no longer appears in new runs.
- **Actor saturation:** `res` and `cap` were both at their minimum in the design that hung. This may mean the actor's outputs saturate at -1, which is not confirmed. Many `simulation failed` lines in a new run would point to this. Each timed-out design also costs 10 seconds.
- **Agent is not saved:** the runner never calls `agent.save`, so the trained networks are lost when a run ends or is stopped. Plots and `solutions/` are kept.
- **ngspice non-convergence:** it can exit with code 0 and give wrong but finite numbers. Those are not detected.
- **`plotLearning` "Running Avg":** `max(0, t-N)` is always 0, so this is the average of all episodes so far, not a sliding window. Use the raw score line to judge performance.
- **`max_reward.png`:** it only updates when a valid design is found. A flat or old plot does not mean the run stopped.
- **Slew rate:** it is measured on rising edges only, to match the TA reference, and uses the signal's min and max, so a feed-through glitch can affect it. Using settled levels is an option for later.

## 5. Practical rules for running

- Run from the project folder with the venv active, because the paths are relative.
- Use a new `--run_id` for each experiment.
- Do not run two trainings at the same time. `clean.sh` empties `no_backup/` every 100 steps and would delete the other run's files.
- Check a long run by looking at the modification time of `output_figs/<run_id>/average_score.png`. It should change every few seconds.
