"""
Unit test for the CAD project, driven by references.csv.

references.csv is "transposed": each ROW is an attribute (param_mp1, spec_gain,
norm_gain, reward, ...) with its unit, and each COLUMN after 'Unit' is one design
(Design 1, Design 2, ...). load_rows() turns it into one dict per design: its 20 sizing parameters, the 7
specs the TAs measured for it, and the reward they computed. This test checks
your code reproduces both.

Run FROM the CAD/ directory (the working dir the wrapper + netlist paths assume):
    cd CAD
    python test_dut.py

It runs two INDEPENDENT checks:

  PART A - measurements (Milestone 1, needs ngspice):
      your DUT, given a row's params, must measure specs close to that row's specs.

  PART B - reward (Milestone 2, NO simulator):
      your circuit_env, given a row's *reference* specs, must compute a reward
      close to that row's reward. Because it uses the TAs' specs as input, a
      mismatch here is purely a reward-logic bug, not a measurement bug.

Part B is skipped automatically until normalize_specs / reward_computation are
implemented (while they're stubs they return None).
"""

import os
import csv
import math

CSV_PATH = os.environ.get("REF_CSV", "references.csv")
REL_TOL  = 0.05   # 5% relative tolerance
ABS_TOL  = 1e-12  # floor so near-zero values (e.g. res=0) don't blow up rel error

# The 20 sizing parameter columns (names must match the CSV headers and the YAML).
PARAM_COLS = [
    'mp1', 'wp1', 'lp1', 'mn1', 'wn1', 'ln1',
    'mp3', 'wp3', 'lp3', 'mn3', 'wn3', 'ln3',
    'mn4', 'wn4', 'ln4', 'mn5', 'wn5', 'ln5',
    'cap', 'res',
]

# measure_metrics() key  ->  key in a design dict (after load_rows strips 'spec_').
# Adjust the right-hand side if the TA headers differ (e.g. 'phase_margin' for phm).
SPEC_COLS = {
    'area':     'area',
    'current':  'current',
    'gain':     'gain',
    'noise':    'noise',
    'phm':      'phm',
    'slewRate': 'slewRate',
    'ugbw':     'ugbw',
}
REWARD_COL = 'reward'   # set to None if the CSV has no reward column

# helper for correct data type
def _num(name, s):
    """m* params are integer multiplicities; everything else is float."""
    return int(float(s)) if name.startswith('m') else float(s)

# helper for accuracy check
def _close(got, ref):
    return abs(got - ref) <= max(REL_TOL * abs(ref), ABS_TOL)


def load_rows(path):
    """
    Read the transposed references.csv and return one dict per design, e.g.
        {'name': 'Design 1', 'mp1': '6', ..., 'gain': '817.2', ..., 'reward': '...'}
    The 'param_' and 'spec_' prefixes are stripped; other attributes
    (action_*, norm_*, reward) keep their name as-is.
    """
    if not os.path.isfile(path):
        print(f"[skip] {path} not found")
        return None
    with open(path, newline='') as f:
        table = list(csv.reader(f))

    header = table[0]                      # ['Attribute', 'Unit', 'Design 1', ...]
    design_names = header[2:]
    rows = [{'name': name} for name in design_names]
    for line in table[1:]:
        if not line or not line[0].strip():
            continue
        attr = line[0].strip()
        for prefix in ('param_', 'spec_'):
            if attr.startswith(prefix):
                attr = attr[len(prefix):]
        for row, value in zip(rows, line[2:]):
            row[attr] = value.strip()
    return rows

# unit test to check the measurements
def part_a_measurements(rows):
    print("\n=== PART A: measurements vs reference (needs ngspice) ===")
    from ngspice_interface.dut_testbench import DUT
    yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                             'files', 'yaml_files', 'TwoStage.yaml')
    dut = DUT(yaml_path)

    failures = []
    for i, row in enumerate(rows):
        params = {p: _num(p, row[p]) for p in PARAM_COLS}
        # new netlist
        netlist = dut.create_new_netlist(params, process='TT', temp_pvt=27, vdd=1.2)
        # simulate the new netlist
        info = dut.simulate(netlist)
        if info != 0:
            print(f"  {row['name']}: ngspice FAILED (info={info})")
            failures.append((i, 'ngspice'))
            continue
        # measure the specs of simulation
        specs = dut.measure_metrics()
        for key, col in SPEC_COLS.items():
            if col not in row:
                continue
            got, ref = float(specs[key]), float(row[col]) # compare measurement with reference
            if not _close(got, ref): # check whether error is in tolerance
                print(f"  {row['name']}: {key:9s} got {got:.6g}  ref {ref:.6g}  MISMATCH")
                failures.append((i, key))
    print(f"Part A: {len(rows)} designs, {len(failures)} mismatches.")
    return failures


def part_b_reward(rows):
    print("\n=== PART B: reward vs reference (no simulator) ===")
    if REWARD_COL is None or REWARD_COL not in rows[0]:
        print("  [skip] no reward column in the CSV.")
        return []
    from circuit_env import CircuitEnv
    env = CircuitEnv(circuit_name='TwoStage', run_id='unittest',
                     simulator='ngspice', success_threshold=0.0)

    # Probe whether the reward path is implemented yet (stubs return None).
    probe_specs = {k: float(rows[0][c]) for k, c in SPEC_COLS.items() if c in rows[0]}
    norm = env.normalize_specs(probe_specs)
    if norm is None:
        print("  [skip] normalize_specs not implemented yet.")
        return []
    if env.reward_computation(norm) is None:
        print("  [skip] reward_computation not implemented yet.")
        return []

    failures = []
    for i, row in enumerate(rows):
        spec_dict = {k: float(row[c]) for k, c in SPEC_COLS.items() if c in row}
        norm = env.normalize_specs(spec_dict)
        reward, _hard = env.reward_computation(norm)
        ref = float(row[REWARD_COL])
        if not _close(reward, ref):
            print(f"  {row['name']}: reward got {reward:.6g}  ref {ref:.6g}  MISMATCH")
            failures.append(i)
    print(f"Part B: {len(rows)} designs, {len(failures)} reward mismatches.")
    return failures


def main():
    rows = load_rows(CSV_PATH)
    if not rows:
        return
    print(f"Loaded {len(rows)} reference designs from {CSV_PATH}.")
    fails_a = part_a_measurements(rows)
    fails_b = part_b_reward(rows)
    assert not fails_a, f"measurement mismatches: {fails_a}"
    assert not fails_b, f"reward mismatches on designs: {fails_b}"
    print("\nAll reference designs passed.")


if __name__ == "__main__":
    main()