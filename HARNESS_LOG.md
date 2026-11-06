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
