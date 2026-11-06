---
name: rl-sizer
description: How to run the TD3 sizer through the cad tools. Use only when hand design found no feasible design.
---

# Running the TD3 sizer

1. `warmup` with 200 steps: random designs fill the replay buffer.
2. `train` with 800 steps, in one call. Simulations cost no tokens, but every call costs a turn.

Warmup must reach at least 100 experiences before training. TD3 rarely finds a feasible design in its first few hundred steps, so short runs are not useful. Run this once, then report, even if nothing is feasible.
