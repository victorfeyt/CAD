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
- UGBW = gm1 / (2 pi Cc), with gm1 = (gm/Id) * Itail/2.
- Second pole = gm2 / (2 pi CL). Rc moves the zero: zero = 1 / (2 pi Cc (Rc - 1/gm2)). Placing it near the second pole recovers phase margin.
- Slew rate is measured on the rising edge only, so it is about Itail/Cc. The PMOS drives that edge, so I2 does not limit it.
- Balance (low offset): (m*w/l of mp3) / (m*w/l of mp1) = 2 * I2 / Itail. If gain is far too low, the second stage is out of balance: adjust mp3 against mn5.
- Area: Cc costs 0.33 um^2 per fF and Rc 1/14 um^2 per ohm. Transistors cost m * w * l plus edges.
- Gain rises with l and lower current. Noise falls with gm1.

## Hand-sizing method
1. Pick a small Cc, because it costs area. Check Itail >= slew rate * Cc.
2. From UGBW and Cc, find gm1, then Itail. Assume gm/Id of 10 to 15 for a first design, and correct it from the measured ugbw.
3. Pick I2 to set gm2, keeping total current low. Set Rc from the zero equation.
4. Set the mirrors from Itail and I2, size the input pair for gm1, then set mp3 from the balance rule.

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
