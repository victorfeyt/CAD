"""
Run FROM the CAD/ directory:
    python -m unittest unit_test_dut -v

TestMeasureMetrics and TestReward are driven by references.csv. That file is
"transposed": each ROW is an attribute (param_mp1, spec_gain, norm_gain, reward, ...)
with its unit, and each COLUMN after 'Unit' is one design (Design 1, Design 2, ...).
load_rows() turns it into one dict per design. unit_test_env.py imports load_rows, _num,
REL_TOL and ABS_TOL from here.
"""

import os
import csv
import unittest
import numpy as np

# The DUT and CircuitEnv build their paths from os.getcwd(), so make sure we're in CAD/.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from circuit_env import CircuitEnv
from ngspice_interface.dut_testbench import DUT

REF_CSV = os.environ.get('REF_CSV', 'references.csv')
REL_TOL = 0.02   # 2% relative tolerance
ABS_TOL = 1e-12  # floor so near-zero values (e.g. res=0) don't blow up rel error

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


def _num(name, s):
    """m* params are integer multiplicities; everything else is float."""
    return int(float(s)) if name.startswith('m') else float(s)


def load_rows(path):
    """
    Read the transposed references.csv and return one dict per design, e.g.
        {'name': 'Design 1', 'mp1': '6', ..., 'gain': '817.2', ..., 'reward': '...'}
    The 'param_' and 'spec_' prefixes are stripped; other attributes
    (action_*, norm_*, reward) keep their name as-is. Returns None if the file
    doesn't exist, so the tests can skip.
    """
    if not os.path.isfile(path):
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


class TestMeasureMetrics(unittest.TestCase):
    """Part A (Milestone 1). Needs ngspice. Simulates each design's param_* with the DUT
    directly (bypassing CircuitEnv) and checks every measured spec against that design's
    spec_* row."""

    @classmethod
    def setUpClass(cls):
        yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                                 'files', 'yaml_files', 'TwoStage.yaml')
        cls.dut = DUT(yaml_path)
        cls.rows = load_rows(REF_CSV)

    def test_matches_references_csv(self):
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            params = {name: _num(name, row[name]) for name in PARAM_COLS}
            # Reset per design: if a step below fails, specs stays None instead of
            # holding the previous design's results.
            specs = None
            with self.subTest(design=row['name']):
                netlist = self.dut.create_new_netlist(params, process='TT',
                                                      temp_pvt=27, vdd=1.2)
                info = self.dut.simulate(netlist)
                self.assertEqual(info, 0, msg='ngspice failed')
                specs = self.dut.measure_metrics()
            if specs is None:
                continue  # the failure is already recorded by the subTest above
            for key, col in SPEC_COLS.items():
                if col not in row:
                    continue  # the CSV has no reference value for this spec
                with self.subTest(design=row['name'], spec=key):
                    got, ref = float(specs[key]), float(row[col])
                    self.assertLessEqual(abs(got - ref), max(REL_TOL * abs(ref), ABS_TOL),
                                         msg=f'{key}: got {got:.6g}, ref {ref:.6g}')


class TestReward(unittest.TestCase):
    """Part B (Milestone 2). No simulator. Feeds each design's *reference* spec_* through
    normalize_specs() and reward_computation() and checks the result against that design's
    reward row. The input is the TAs' specs, so a mismatch here is purely a reward-logic
    bug, not a measurement bug."""

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest',
                             simulator='ngspice', success_threshold=0.0)
        cls.rows = load_rows(REF_CSV)

    def _spec_dict(self, row):
        return {key: float(row[col]) for key, col in SPEC_COLS.items() if col in row}

    def test_matches_references_csv(self):
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        if REWARD_COL is None or REWARD_COL not in self.rows[0]:
            self.skipTest(f'no reward column in {REF_CSV}')
        # Skip while normalize_specs / reward_computation are still stubs that return None.
        norm_specs = self.env.normalize_specs(self._spec_dict(self.rows[0]))
        if norm_specs is None:
            self.skipTest('normalize_specs not implemented yet')
        if self.env.reward_computation(norm_specs) is None:
            self.skipTest('reward_computation not implemented yet')

        for row in self.rows:
            norm_specs = self.env.normalize_specs(self._spec_dict(row))
            reward, _ = self.env.reward_computation(norm_specs)
            ref = float(row[REWARD_COL])
            with self.subTest(design=row['name']):
                self.assertLessEqual(abs(reward - ref), max(REL_TOL * abs(ref), ABS_TOL),
                                     msg=f'reward: got {reward:.6g}, ref {ref:.6g}')


class TestGain(unittest.TestCase):
    """No simulator. Feeds hand-made AC responses straight into find_dc_gain() (bypassing
    ngspice and parse_outputs) and checks it returns |vout| at the first sweep point."""

    @classmethod
    def setUpClass(cls):
        yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                                 'files', 'yaml_files', 'TwoStage.yaml')
        cls.dut = DUT(yaml_path)

    def test_real_positive_vout(self):
        # In-phase output: the gain is just vout at the first (lowest-frequency) point.
        vout = np.array([100, 80, 10], dtype=complex)
        self.assertAlmostEqual(self.dut.find_dc_gain(vout), 100.0, places=12)

    def test_inverting_vout_gives_positive_gain(self):
        # An inverting amplifier has vout < 0 at DC (180 deg phase). Gain is a magnitude,
        # so -150 V/V must give 150, not -150.
        vout = np.array([-150, -120, -40], dtype=complex)
        self.assertAlmostEqual(self.dut.find_dc_gain(vout), 150.0, places=12)

    def test_complex_vout_gives_magnitude(self):
        # With some phase shift at the first point, the gain is |3 + 4j| = 5, not the real
        # part 3, and it comes back as a real float rather than a complex number.
        gain = self.dut.find_dc_gain(np.array([3 + 4j, 1 + 1j]))
        self.assertIsInstance(gain, float)
        self.assertAlmostEqual(gain, 5.0, places=12)

    def test_only_first_point_is_used(self):
        # Higher-frequency points must not leak in, even when they are larger (with a low
        # phase margin, the peak of the response can exceed the DC gain).
        vout = np.array([2, 1000, -1e6], dtype=complex)
        self.assertAlmostEqual(self.dut.find_dc_gain(vout), 2.0, places=12)

    def test_single_pole_sweep(self):
        # Realistic input: an inverting OTA with A0 = 817 V/V and its pole at 350 kHz (close
        # to Design 1), sampled like the netlist's 'ac dec 10 1 1T'. The first point is at
        # 1 Hz, far below the pole, so the measured gain equals A0 to within 1 ppm.
        a0, f_pole = 817.0, 350e3
        freq = np.logspace(0, 12, 121)
        vout = -a0 / (1 + 1j * freq / f_pole)
        self.assertAlmostEqual(self.dut.find_dc_gain(vout), a0, delta=1e-6 * a0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
