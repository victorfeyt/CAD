Size this two-stage Miller op-amp from scratch.

Circuit (45 nm, VDD = 1.2 V, CL = 10 pF, Ibias = 30 uA into the bias diode, input common mode 0.6 V):
- mn1 (wn1, ln1): NMOS input pair M1/M2, sharing a tail node.
- mp1 (wp1, lp1): PMOS mirror load M3/M4 of the input pair.
- mn3 (wn3, ln3): NMOS bias diode, fed by Ibias.
- mn4 (wn4, ln4): NMOS tail source M5, mirrors mn3.
- mp3 (wp3, lp3): PMOS common-source second stage M6, gate on the first-stage output.
- mn5 (wn5, ln5): NMOS second-stage sink M7, mirrors mn3.
- cap and res: Miller capacitor Cc in series with Rc, from the first-stage output to the output.

Grids: m 1..24; w 0.25u..2.75u step 0.25u; l 45n..180n step 45n; cap 0.1p..9.9p step 0.1p; res 0..9.8k step 100.

Hard specs: gain >= 200, noise <= 0.03, phm >= 60 deg, slewRate >= 30 V/us, ugbw >= 100 MHz.
Objectives: minimise current (target 200 uA) and area (target 2e-9 m^2).
Scoring: a feasible design beats an infeasible one. Beyond that, the reward keeps rising as current and area fall below their targets. The simulator is deterministic, at the nominal corner only.

Never read files; use only the cad tools and your skills.
