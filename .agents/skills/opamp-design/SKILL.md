---
name: opamp-design
description: Circuit knowledge for the two-stage Miller op-amp. Use when choosing or changing transistor sizes, or explaining why a spec passes or fails.
---

# Two-stage Miller op-amp (45 nm, VDD 1.2 V, CL 10 pF, Ibias 30 uA)

## Parameters
- `mn1,wn1,ln1`: NMOS input pair. `mp1,wp1,lp1`: PMOS mirror load.
- `mn3,wn3,ln3`: bias diode. `mn4,wn4,ln4`: tail source. `mn5,wn5,ln5`: second-stage sink.
- `mp3,wp3,lp3`: PMOS common-source second stage. `cap`: Cc. `res`: Rc.
- Grids: m 1..24; w 0.25u..2.75u step 0.25u; l 45n..180n step 45n; cap 0.1p..9.9p step 0.1p; res 0..9.8k step 100.

## Equations
- Mirror: I = 30uA * (m*w/l of mn4 or mn5) / (m*w/l of mn3). Current = 30uA + Itail + I2.
- UGBW is about gm1 / (2 pi Cc), and gm/Id is only about 8 at these sizes. It also rises with res and I2.
- Second pole gm2/(2 pi CL) is below UGBW, so Rc adds a left-half-plane zero: more res raises phm and ugbw but costs area.
- Slew rate is measured on the rising edge only, so it is about Itail/Cc. The PMOS drives that edge, so I2 does not limit it.
- Output bias: m*w of mp3 about 0.83 * m*w of mn5, at equal l. If they mismatch by more than about 10%, gain collapses to about 200.
- Area: Cc costs 0.33 um^2 per fF and Rc 1/14 um^2 per ohm, so these two dominate. Transistors cost m * w * l plus edges.
- Gain rises with l and lower current. Noise falls with gm1.

## Hand-sizing recipe
Calibrated rules for this process; compute the sizes from them.
1. l = 90n everywhere. Bias diode m*w = 4 um. Mirror load m*w = 4 um.
2. Cc = 0.5 pF, Rc = 4.5 kohm.
3. Itail = 90 uA and I2 = 180 uA, set by the mirror ratios.
4. Input pair m*w about 8-12 um. Then mp3 from the output bias rule.

## What to change
| Failing | Change |
|---|---|
| ugbw | Lower cap, raise Itail or the input pair size |
| phm | Raise res, raise I2 and mp3 |
| slewRate | Raise Itail, lower cap |
| gain | Raise l, lower current |
| noise | Raise input pair size or Itail |
| current high | Lower I2 first, then Itail, while phm holds |
| area high | Lower res and cap together, keeping phm |
