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
- UGBW = gm1 / (2 pi Cc), with gm1 about 15 * Itail/2 in moderate inversion.
- Phase margin: second pole gm2/(2 pi CL) is below UGBW here, so Rc must add a left-half-plane zero near it: Rc about (CL + Cc) / (gm2 * Cc).
- Slew rate is measured on the rising edge only, so it is about Itail/Cc. The PMOS drives that edge, so I2 does not limit it.
- Balance (low offset): (w/l of mp3 * mp3) / (w/l of mp1 * mp1) = 2 * I2 / Itail.
- Area: Cc costs 0.33 um^2 per fF and Rc 1/14 um^2 per ohm, so these two dominate (0.6 pF = 200 um^2, 3 kohm = 214 um^2). Transistors cost m * w * l plus edges.
- Gain rises with l and lower current. Noise falls with gm1.

## Hand-sizing recipe
1. Pick Cc about 0.6 pF (small area) and l = 90n everywhere.
2. Itail from UGBW above 100 MHz with margin, about 60 uA. I2 about 150 uA.
3. Set the mirrors from Itail and I2, the input pair for high gm1, then mp3 from the balance rule.
4. Set Rc from the zero equation with gm2 about 15 * I2.

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
