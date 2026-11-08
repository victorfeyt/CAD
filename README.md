## Running the harness

Run from the project folder with the venv active. Make sure `solutions/`, `output_figs/` and `references.csv` are not in the folder.
The output goes to a json file, so the terminal shows nothing while the run is busy.

### RL off (default: hand design and review, at most about 28 simulations)
macOS / Linux:
```
agy -p "$(cat PROMPT.md)" --agent sizing-lead --model gemini-3.8-flash-high --output-format json --print-timeout 400s --settings '{"permissions":{"allow":["mcp(cad/*)"]}}' > run5.json
```
Windows PowerShell:
```
agy -p (Get-Content PROMPT.md -Raw) --agent sizing-lead --model gemini-3.8-flash-high --output-format json --print-timeout 400s --settings '{\"permissions\":{\"allow\":[\"mcp(cad/*)\"]}}' > run5.json
```
TD3 runs only as a fallback, if the hand design is not feasible.

### RL on (TD3 always runs after the designer, about 1,100 extra simulations)
macOS / Linux:
```
agy -p "$(cat PROMPT.md) RL mode: on." --agent sizing-lead --model gemini-3.8-flash-high --output-format json --print-timeout 600s --settings '{"permissions":{"allow":["mcp(cad/*)"]}}' > run6.json
```
Windows PowerShell:
```
agy -p ((Get-Content PROMPT.md -Raw) + " RL mode: on.") --agent sizing-lead --model gemini-3.8-flash-high --output-format json --print-timeout 600s --settings '{\"permissions\":{\"allow\":[\"mcp(cad/*)\"]}}' > run6.json
```
**Windows note:** the `train` tool in `sizing_tools.py` calls `./clean.sh`, which fails on Windows. Run RL on with macOS, or replace that call with `clean_no_backup()` from `td3_runner.py`.

### Prompt
- The file **`PROMPT.md`** holds everything specific to this circuit:
  - the circuit (VDD, CL, Ibias, vcm) and which parameter is which device
  - the grids, the hard specs, the current and area targets, and how scoring works
- The circuit facts are deliberately in the prompt, not in the skill.

### Skill
- **`analog-sizing`** (`.agents/skills/analog-sizing/SKILL.md`).
- It holds only general design rules that apply to any analog circuit:
  - Give every device a role. Matched devices share w and l, and ratios are set with m.
  - L of about 2 to 3 times Lmin, and gm/Id per role: input 15 to 20, mirrors 5 to 10, gain stage 10 to 15.
  - General equations for gain, poles, phase margin, slew rate, noise, current, area and DC balance.
  - Hand calculation first. The first simulation serves as calibration, then the design is scaled.
  - Iterate with few LLM turns, with several simulations in parallel per turn.
  - Open-loop testbench: the output is sensitive to balance. If gain or ugbw suddenly collapses, sweep the balancing device finely with w.
- **`rl-sizer`** (`.agents/skills/rl-sizer/SKILL.md`).
- It explains how to run the TD3 sizer through the `cad` tools, and is meant only for when hand design finds no feasible design:
  - `warmup` with 200 steps: random designs fill the replay buffer. Training needs at least 100 experiences.
  - `train` with 800 steps, in one call. Simulations cost no tokens, but every call costs an LLM turn.
  - TD3 rarely finds a feasible design in its first few hundred steps, so short runs are not useful.
  - Run it once, then report, even if nothing is feasible.

### Agents (`.agents/agents/`)
- **All subagents** reply only with a fixed *result card*, so little text passes between agents:
  ```
  RESULT feasible= reward= limiting= sims=
  PARAMS (all 20)
  SPECS gain= ugbw= phm= slewRate= noise= current= area=
  STEPS one line per batch: what changed, why, effect (with numbers)
  LEARNED one line: what controls the limiting spec
  ```
- **sizing-lead:**
  - Passes the prompt word for word to the subagents, and only the cards between agents.
  - Decides on RL from the RL mode flag, see below.
  - The final report contains every STEPS line, copied word for word, as the decision trail for explainability.
- **designer:** uses `analog-sizing` skill, one calibration simulation, then at most 3 batches of 2 to 4 parallel variants (at most 10 simulations). It stops at the first feasible design.
- **reviewer:**
  - Knows the reward formula for a feasible design: 0.3 + m(current) + m(area).
  - Uses margins of 1 to 3 % on the hard specs, since the simulator is deterministic.
  - At most 3 batches of 4 to 6 parallel variants (at most 18 simulations).
  - If RL ran, it explains why the RL design differs from the hand design.
- **rl-operator:** runs TD3 with the `rl-sizer` skill, (warmup 200, train 800). It copies `simulator_calls` from the tool result, so the simulation count is correct.

### After each run
- Re-simulate the final parameters once, and check that the specs match.
- Note the tokens (`usage.total_tokens`), `simulator_calls` and `duration_seconds` in `HARNESS_LOG.md`.
- Every agy run uses our shared token budget, so only run what is needed.

## Results of all runs
All runs start from scratch. Feasible results were checked by re-simulating them locally. Run outputs and the log are in `../CAD_results/`.

| Run | Model | Setup / what happened | Feasible | Reward | Simulations | Tokens | Time |
|---|---|---|---|---|---|---|---|
| run1 | flash-low | old setup, through the TD3 fallback | yes | 0.305 | 1,104 | 115k | 111 s |
| run2 | flash-low | generic skill, result cards | yes | 0.620 | 19 | 213k | 102 s |
| run4 | flash-low | RL mode on; same TD3 design as run1 (same seed); reviewer skipped | yes | 0.305 | 1,108 | 149k | 130 s |
| run5 | flash-low | TD3 fallback, but a shorter run than instructed | yes | 0.135 | 446 | 111k | 76 s |
| run6 | flash-low | lead announced RL as text, which ended the run | no | −0.272 | 10 | 173k | 88 s |
| run7 | flash-high | timed out, then resumed; phm 0.75° short; lead skipped RL and the reviewer | no | 0.013 | 25 | 318k | 546 s |
| run8 | flash-low | fixed flow: TD3, then the reviewer repaired the slew rate (Cc 4.1 → 2.8 pF) | yes | 0.001 | 286 | 200k | 103 s |
| run9 | flash-high | used `send_message` instead of the subagent tool, so no design | – | – | 0 | 243k | 424 s |
| run10 | flash-high | **best run**; a denied `read_file` stopped it once, then resumed | yes | **0.621** | 19 | 294k | 692 s |
| run11 | flash-medium | hand design feasible in 9 sims; reviewer did not try to improve | yes | 0.567 | 9 | 186k | 214 s |

**Fixes after the failures:**
- a mandatory agent order (run6, run7)
- the `send_message` ban (run9)
- the rule against reading files (run10)
- "always at least one reviewer batch" (run11)

**Best design (run10):**
- **Sizes:** mn1 5/2u/90n, mp1 1/2u/90n, mn3 1/1u/90n, mn4 2/1u/90n, mp3 6/2u/90n, mn5 6/1u/90n. Cc 0.3 pF, Rc 9 kΩ.
- **Specs:** gain 630, ugbw 100.09 MHz, phm 62.65°, current 258 µA, area 762 µm².
