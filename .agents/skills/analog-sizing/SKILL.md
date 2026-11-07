---
name: analog-sizing
description: General method for sizing any analog CMOS circuit in any technology with few simulations. Use when choosing or changing transistor sizes, or explaining why a spec passes or fails.
---

# Analog sizing method

## 1. Understand the circuit before sizing
- Give every device a role: input device, load, current source or mirror, bias reference, gain stage, output stage, or compensation.
- Find the signal path, the high-impedance nodes (these set poles and gain), and the branches that draw supply current.
- For each spec, write down which roles control it.

## 2. Shrink the search space
- **Matched devices:** devices that must match share w and l. Set current ratios only with the multiplier m, so ratios stay exact.
- **Length:** start at about 2 to 3 times Lmin for analog devices. Use Lmin only where speed matters and gain does not. Longer l gives more gm/gds and better matching, but more area and capacitance.
- **gm/Id per role:** this fixes each device's operating point, independent of the technology.
  - Input devices: high gm/Id (moderate inversion, about 15 to 20). Most gm per current, low noise, low offset.
  - Current sources, mirrors and loads: low gm/Id (strong inversion, about 5 to 10). Better matching, higher output resistance per area, less noise.
  - Gain and output stages: medium gm/Id (about 10 to 15).
- With l and gm/Id fixed, the free variables are only the branch currents and the passives. Width follows the current at the chosen gm/Id.
- **Scaling:** scaling the current and m*w of a device by the same factor keeps gm/Id, scales gm with the current, and keeps gm/gds.

## 3. Equations that hold for any amplifier
- Gain per stage is about gm/(sum of gds at the output node). Total gain is the product over the stages.
- Bandwidth: GBW = gm(input) / (2 pi C at the dominant node). Each pole is gm / (2 pi C) of its node.
- Phase margin: non-dominant poles must lie well above GBW. A single non-dominant pole at 2.2 GBW gives about 60 degrees. Right-half-plane zeros cost phase; left-half-plane zeros add phase.
- Compensation (Miller or other): a larger compensation C lowers GBW and raises phm. A series resistor moves the zero; tune it to cancel or pass the first non-dominant pole.
- Slew rate: the current available to charge each capacitor, I/C. The slowest node limits it.
- Noise: the first stage dominates. Raise input gm and device area (m*w*l), keep load gm low. Output-referred noise also scales with the gain.
- Current: the sum of all branch currents. Area: passives are usually expensive; transistors cost about m*w*l.
- DC balance: mirrored currents must agree with the currents the devices draw. A mismatch pushes devices out of saturation and collapses the gain.
- Open-loop testbench: the output DC level is the systematic offset times the gain. In a high-gain amplifier, one grid step on the balancing device can drive the output to a rail. Symptoms: a sudden collapse of gain or bandwidth, or a supply current that moves more than the mirrors predict. Fix: sweep the balancing device finely, with w steps rather than m steps, in parallel variants.

## 4. Hand design, then calibrate
1. From the specs and the equations, find the required gm of each critical device, with a margin of about 20 % on the targets.
2. Get the currents from gm and the gm/Id role. Get the widths from the currents and the mirror ratios.
3. Check the current and area estimates against the targets before simulating.
4. Device constants are unknown at first. Treat the first simulation as calibration: compare the measured specs with the hand estimates, and correct the gm, gds and capacitance assumptions.
5. Then scale the design from the corrected equations. Do not guess again from scratch.

## 5. Iterate with few LLM turns
- **Batch:** simulations are cheap and turns are expensive. Issue several `simulate` calls in the same response, as variants of one idea: different strengths of one change, or a fine sweep of one parameter.
- **Hard constraints first:** fix the failing spec with the worst relative margin, using the role that controls it most directly.
- **Coordinated changes:** move matched devices and balance conditions together, so a fix does not break DC balance.
- **One cause per step:** change the parameters for one reason per simulation, so the result explains itself.
- **Large changes when far off:** scale by the ratio the equation predicts, not by grid steps.
- **Spend the margins:** once feasible, turn surplus margin on one spec into lower current or area. Break the current down per branch and the area per element, attack the largest item first, and recover the limiting spec with the cheapest parameter.
- **Record each step:** what changed, why, and what it did. Check the trend matches the equation; if it does not, revise the assumption.

## Quick table
| Failing | Typical fix |
|---|---|
| Bandwidth | Raise the gm of the device that sets the limiting pole, or lower that node's capacitance |
| Phase margin | Separate the poles: raise non-dominant gm, raise compensation, tune the zero |
| Slew rate | Raise the current into the limiting capacitor, or lower that capacitor |
| Gain far too low | DC balance is broken: correct the mirror ratios and device sizes |
| Gain slightly low | Raise l or gm/Id of the gain devices |
| Noise | Raise input gm and area, lower load gm, avoid excess gain |
| Current high | Lower the branch current with the most margin, and recover with passives |
| Area high | Lower passives, then l and m*w of large devices |
