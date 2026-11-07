# LLM harness log

Last updated: 2026-11-06. Companion to `KNOWN_ISSUES.md`. Status: **runs end to end, but too many tokens**.

## What exists
| File | Purpose |
|---|---|
| `AGENTS.md` | Rules for every agent: specs, no reading earlier results, few turns |
| `.agents/agents/sizing-lead.md` | Main agent, delegates to the others |
| `.agents/agents/designer.md` | Hand-sizes the design, at most 3 simulations |
| `.agents/agents/reviewer.md` | Looks for wasted margin, at most 2 simulations |
| `.agents/agents/rl-operator.md` | Runs TD3 only if no design is feasible |
| `.agents/skills/opamp-design` | Circuit equations, hand-sizing recipe, what to change per failing spec |
| `.agents/skills/rl-sizer` | How to run TD3 |

The agents use only the four original tools: `simulate`, `warmup`, `train`, `get_status`.

## Removed
`refine`, `simulate_batch`, the `reason` argument, compact output, tool logging and `run_harness.sh` were tried and removed. `mcp_server.py` must not be changed, and the basics come first. `mcp_server.py` and `sizing_tools.py` match commit `3066bf2`.

## Measured
With `agy --output-format json` on `gemini-3.8-flash-low`:

| Check | Tokens |
|---|---|
| One turn that did nothing useful | 16,299 |
| Tool call, then one subagent making one tool call | 61,323 |

So each LLM call costs about 16,000 tokens, and subagents add calls. The four-agent setup is therefore likely to cost much more than a single agent.

## First full run
Command, from the project folder:

    agy -p "Size the op-amp from scratch." --agent sizing-lead --model gemini-3.8-flash-low --output-format json --print-timeout 280s --settings '{"permissions":{"allow":["mcp(cad/*)"]}}'

| Result | Value |
|---|---|
| FoM | 0.6644, feasible |
| Simulations | 1 according to the report |
| Tokens | 184,103 total, of which 12,393 thinking and 62,667 cache reads |
| Runtime | 169 s |

**This run is not a valid from-scratch result.** It used a recipe calibrated with about 28 simulations outside the run. The jury tests the LLM with no history and no staged values, so those numbers were removed from `opamp-design`, which now holds only general theory and a method. No run has been done with this version, and the first design will likely be worse.

## Facts for setup
- Subagents with `inheritCustomizations: true` reach the parent's `cad` server and share its state: both calls returned the same `run_id`.
- Headless runs need `mcp(cad/*)` in `permissions.allow`. `--mode auto` is not available on this account.
- `agy --output-format json` reports token use and duration.

## Open
- `sizing_tools.py` calls `./clean.sh`, which stops a batch on Windows. `clean_no_backup()` in `td3_runner.py` works on both.
- `sizing_tools.py` pushes `done`, while `td3_runner.py` pushes `False`.

## 2026-11-07: hand-sizing method made concrete
- `opamp-design` now contains:
  - A technology table from a DC sweep of single NMOS and PMOS devices in ngspice: current per um at gm/Id 18, 12 and 8, and gm/gds at L = 90n and 180n. This is datasheet-style device data, not an op-amp design.
  - Corrected circuit behaviour. With CL = 10 pF, UGBW is limited by the second pole (about 4 to 5 times p2 with a good Rc), not by gm1/Cc. Noise is output-referred, so it rises with the gain. Breaking the balance collapses the gain to about 40.
  - A numbered hand-sizing method with formulas and ranges: l = 90n, Cc 0.3 to 1 pF, Rc 5 to 9 kOhm, Itail 50 to 100 uA.
- Basis: about 35 local simulations of the circuit outside the harness, used to check the trends and the factor of 4 to 5. No complete design is stored in the skill.
- Check: following the method by hand gave a feasible first design (gain 665, ugbw 121 MHz, phm 66.8, SR 62.9, noise 0.025, I 261 uA, area 701 um^2). Not run in agy.
- Budgets: designer from 3 to 6 simulations, reviewer from 2 to 3.
- **Open question:** whether the jury sees ranges tuned from local simulations as allowed expert knowledge or as staged values.

## 2026-11-07: skill made generic
- Concrete values are not allowed. `opamp-design` now holds only guidelines that apply to any technology:
  - L of 2 to 3 times Lmin.
  - gm/Id per role: input pair 15 to 20, mirrors 5 to 10, second stage 10 to 15.
  - Mirror matching through m.
  - Textbook two-stage Miller rules: p2 >= 2.2 GBW and the Rc zero placement.
  - The balance rule, noise trends, and calibrating the design on the first simulation.
- Removed: the technology table, Vth values, the "4 to 5 times p2" factor, and the ranges for Cc, Rc and Itail.
- Kept: the parameter grids and the circuit definition (VDD, CL, Ibias), because the tools require them and the agent cannot read the source.

## 2026-11-07: circuit facts moved to the prompt
- `opamp-design` is now generic for any two-stage Miller op-amp. It uses device roles (M1 to M7, Cc, Rc) instead of parameter names, and it contains no supply, load, bias or grid values.
- `PROMPT.md` holds the circuit: 45 nm, VDD, CL, Ibias, vcm, the mapping from parameter names to roles, and the grids. Hard specs stay in `AGENTS.md`.
- `sizing-lead` passes the full circuit description to `designer` and `reviewer`, because subagents do not see the user's prompt.
- Run (macOS): agy -p "$(cat PROMPT.md)" --agent sizing-lead ...
- Run (Windows PowerShell): agy -p (Get-Content PROMPT.md -Raw) --agent sizing-lead ...

## 2026-11-07: skill made topology-independent
- `opamp-design` is renamed to `analog-sizing`, and `designer.md` is updated.
- The skill is now a general method for any analog circuit in any technology:
  1. Give every device a role.
  2. Shrink the search space: matched devices share w and l and differ only in m; L of 2 to 3 Lmin; gm/Id per role; free variables are only the currents and the passives.
  3. General equations: gain, poles, phase margin, slew rate, noise, current and area.
  4. Hand design, with the first simulation used as calibration.
  5. Iteration rules: hard constraints first, coordinated changes, one cause per step, spend surplus margins, record each step.
- Everything specific to the circuit is in `PROMPT.md`.

## 2026-11-07: prompt, handoff and reviewer changes
- `PROMPT.md` now also holds the hard specs, the objectives with targets, and how scoring works: feasibility first, then lower current and area, at a deterministic nominal corner.
- Handoff: every subagent replies only with a fixed result card: RESULT/PARAMS/SPECS/STEPS/LEARNED. The lead copies the prompt word for word and passes only the cards.
- `sizing-lead`:
  - RL decision with a one-line reason: RL runs if the hand design is infeasible, or if its current or area is above 1.5 times the target. Otherwise RL is skipped.
  - The reviewer always works on the best card.
  - The final report lists every STEPS line as the decision trail.
- `designer`: at most 6 simulations, stops at the first feasible design, uses the first simulation as calibration.
- `reviewer`: thin margins of 1 to 3 %, cuts predicted from margin ratios, 3 parallel variants per turn, at most 6 simulations in 2 turns.
- `rl-operator`: returns a card with how the RL design differs from the hand design. The `rl-sizer` skill is unchanged.
- Not done, by choice: changes to the TD3 start, behaviour cloning, and per-agent `tools` restrictions.

## 2026-11-07: run2, and changes for more simulations with fewer turns
Run2 (`agy -p "$(cat PROMPT.md)" --agent sizing-lead`, flash-low):

| Result | Value |
|---|---|
| Reward | 0.6195, feasible |
| Simulations | 19 |
| Tokens | 212,765 (207k of them input) |
| Time | 102 s |

- Re-simulated locally: gain 712, ugbw 120 MHz, phm 60.1, SR 61.8, noise 0.0163, I 320 uA, area 581 um^2.
- Reward = 0.3 + 0.55 (area) - 0.23 (current).
- Problems:
  - The lead skipped RL at 1.6 times the current target, against its 1.5 times rule.
  - The STEPS lines were paraphrased, without numbers.
  - The output was not saved, because agy only prints to stdout.
- Local sweep around the run2 design: in the open-loop testbench, one m step on mp3 rails the output. Gain and ugbw collapse, and the current changes by about 130 uA. Cutting the current needs a fine sweep of the balancing device.

Changes:
- Skill:
  - Open-loop balance sensitivity: symptoms, and the fix of sweeping finely with w steps in parallel.
  - Batch simulations per response.
  - Break down current and area before cutting.
- Designer: 1 calibration simulation, then at most 3 batches of 2 to 4 parallel variants; at most 10 simulations.
- Reviewer:
  - Uses the reward formula for feasible designs, so it trades current against area.
  - At most 3 batches of 4 to 6 parallel variants; at most 18 simulations.
  - Re-centres the balance when a variant jumps.
- Lead: RL thresholds as absolute numbers (300 uA, 3e-9 m^2), and STEPS lines copied word for word.

## 2026-11-07: RL mode flag
- RL steps count as simulations: one RL run is about 1,100 simulator calls (1,000 steps plus a reset every 10 steps), against at most about 28 without RL.
- Flag in the prompt: add "RL mode: on" to always run TD3 after the designer, and pass both cards to the reviewer. Without the flag, TD3 only runs as a fallback when the hand design is infeasible.
- The rl-operator now copies `simulator_calls` from the tool result into STEPS.
- Run without RL:
  agy -p "$(cat PROMPT.md)" ...
- Run with RL:
  agy -p "$(cat PROMPT.md) RL mode: on." ...
