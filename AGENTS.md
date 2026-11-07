# Op-amp sizing harness

Goal: size the two-stage Miller op-amp with the `cad` MCP tools. A feasible design comes first. Tokens and simulations are also scored, so be brief.

Hard constraints: gain >= 200, noise <= 0.03, phm >= 60, slewRate >= 30, ugbw >= 100e6.
Then minimise area (target 2e-9) and current (target 2e-4). Higher reward is better; satisfactory designs score above unsatisfactory ones in most cases, so check `hard_constraints_satisfied`.

Rules:
- Start from nothing. Never read `solutions/`, `output_figs/`, `references.csv` or source code.
- Use only the `cad` tools and your skills. Never read, list or search files (no read_file or similar): headless runs deny it and the run ends.
- Every LLM turn is expensive: use as few tool calls as possible. Call `get_status` with k=1.
- Keep replies short: results and the reasoning behind decisions only.
