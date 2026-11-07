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

class TestUGBW(unittest.TestCase):
    """No simulator. Feeds hand-made AC responses straight into find_ugbw() (bypassing
    ngspice and parse_outputs) and checks it returns the correct UGBW."""

    @classmethod
    def setUpClass(cls):
        yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                                 'files', 'yaml_files', 'TwoStage.yaml')
        cls.dut = DUT(yaml_path)

    def test_ugbw_at_1hz(self):
        # Gain crosses 1 V/V at 1 Hz.
        freq = np.array([0.1, 0.5, 1.0, 2.0, 5.0])
        vout = np.array([10, 2, 1, 0.5, 0.2], dtype=complex)
        self.assertAlmostEqual(self.dut.find_ugbw(freq, vout), 1.0, places=12)

    def test_ugbw_at_100hz(self):
        # Gain crosses 1 V/V at 100 Hz.
        freq = np.array([10, 50, 100, 200, 500])
        vout = np.array([10, 2, 1, 0.5, 0.2], dtype=complex)
        self.assertAlmostEqual(self.dut.find_ugbw(freq, vout), 100.0, places=12)

    def test_single_pole_inverting_amp_between_grid_points(self):
        # Realistic case: an inverting single-pole amp H(f) = -A0 / (1 + j f/fp) on a
        # log sweep (10 pts/decade). The analytic UGBW is fp*sqrt(A0^2 - 1) ~= 23 MHz,
        # which falls between sample points, so this exercises the log-axis interpolation
        # and checks the negative/complex vout is handled through its magnitude.
        A0, fp = 1000.0, 23e3
        freq = np.logspace(0, 10, 101)
        vout = -A0 / (1 + 1j * freq / fp)
        expected = fp * np.sqrt(A0**2 - 1)
        self.assertFalse(np.any(np.isclose(freq, expected, rtol=1e-3)))  # really off-grid
        self.assertAlmostEqual(self.dut.find_ugbw(freq, vout) / expected, 1.0, places=2)

    def test_no_unity_crossing_returns_zero(self):
        # If |vout| never crosses 1 V/V inside the sweep there is no UGBW, and find_ugbw
        # must report 0.0 (a clearly failing value) instead of the sweep's end frequency.
        freq = np.logspace(0, 6, 7)
        cases = {
            'gain_always_above_1': np.array([1e4, 5e3, 1e3, 500, 100, 20, 2], dtype=complex),
            'gain_always_below_1': np.array([0.9, 0.8, 0.5, 0.2, 0.1, 0.05, 0.01], dtype=complex),
        }
        for name, vout in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.dut.find_ugbw(freq, vout), 0.0)


class TestPhaseMargin(unittest.TestCase):
    """No simulator. Feeds analytic multi-pole AC responses into find_phm() and compares
    against the closed-form phase margin PM = 180 - sum(atan(f_u / p_i))."""

    FREQ = np.logspace(0, 10, 501)  # 50 pts/decade, 1 Hz .. 10 GHz

    @classmethod
    def setUpClass(cls):
        yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                                 'files', 'yaml_files', 'TwoStage.yaml')
        cls.dut = DUT(yaml_path)

    @staticmethod
    def _response(A0, poles, freq):
        """H(f) = A0 / prod(1 + j f/p_i). A negative A0 gives an inverting amplifier."""
        h = np.full(freq.shape, A0, dtype=complex)
        for p in poles:
            h /= 1 + 1j * freq / p
        return h

    @staticmethod
    def _analytic_pm(A0, poles):
        """Solve |H(f_u)| = 1 exactly: with x = f^2, prod(1 + x/p_i^2) - A0^2 = 0 is a
        polynomial in x. Returns (f_u, PM in degrees)."""
        poly = np.array([1.0])
        for p in poles:
            poly = np.polymul(poly, [1 / p**2, 1.0])
        poly[-1] -= A0**2
        x = [r.real for r in np.roots(poly) if abs(r.imag) < 1e-9 * abs(r) and r.real > 0]
        fu = np.sqrt(x[0])
        return fu, 180.0 - sum(np.degrees(np.arctan(fu / p)) for p in poles)

    def test_two_pole_amp_near_60_degrees(self):
        # Textbook two-stage Miller response: dominant pole at 10 kHz, non-dominant pole
        # placed so the PM sits just above the phm >= 60 spec boundary (~62.5 deg). The result
        # must match the closed form to within 0.5 deg, tight enough to judge pass/fail.
        A0, poles = 1000.0, [10e3, 17e6]
        _, expected = self._analytic_pm(A0, poles)
        self.assertGreater(expected, 60.0)
        pm = self.dut.find_phm(self.FREQ, self._response(A0, poles, self.FREQ))
        self.assertAlmostEqual(pm, expected, delta=0.5)

    def test_inverting_amp_has_same_pm(self):
        # An inverting amp starts at 180 deg instead of 0 deg. PM must be measured
        # relative to the DC phase, so flipping the sign of the gain must not change it.
        # (Without that reference the result would be off by 180 deg.)
        A0, poles = 1000.0, [10e3, 17e6]
        pm_noninv = self.dut.find_phm(self.FREQ, self._response(A0, poles, self.FREQ))
        pm_inv = self.dut.find_phm(self.FREQ, self._response(-A0, poles, self.FREQ))
        self.assertAlmostEqual(pm_inv, pm_noninv, places=9)
        self.assertAlmostEqual(pm_inv, self._analytic_pm(A0, poles)[1], delta=0.5)

    def test_unstable_three_pole_amp_gives_negative_pm(self):
        # Two coincident non-dominant poles at 2 MHz push the phase past -180 deg (at
        # 2 MHz) before the gain reaches unity (~3 MHz), so PM is about -23 deg. np.angle
        # wraps from -180 to +180 there; without unwrapping, PM would come out as ~+337 deg
        # and an unstable amplifier would look extremely stable.
        A0, poles = 1000.0, [10e3, 2e6, 2e6]
        _, expected = self._analytic_pm(A0, poles)
        self.assertLess(expected, 0.0)
        pm = self.dut.find_phm(self.FREQ, self._response(A0, poles, self.FREQ))
        self.assertAlmostEqual(pm, expected, delta=0.5)


class TestSlewRate(unittest.TestCase):
    """No simulator. Feeds hand-made transient waveforms into find_slew_rate() and checks
    the 10%-90% slew rate (default unit V/us)."""

    @classmethod
    def setUpClass(cls):
        yaml_path = os.path.join(os.getcwd(), 'ngspice_interface',
                                 'files', 'yaml_files', 'TwoStage.yaml')
        cls.dut = DUT(yaml_path)

    def test_linear_ramp_off_grid_and_time_units(self):
        # Slew-limited step: 0 -> 1.2 V in 40 ns = exactly 30 V/us (the spec boundary).
        # The 3 ns sample grid does not hit the 10%/90% times (14 ns, 46 ns), so the
        # crossings must be interpolated. The same edge in other units must scale exactly.
        t = np.arange(0, 100e-9, 3e-9)
        v = np.interp(t, [0, 10e-9, 50e-9, 100e-9], [0, 0, 1.2, 1.2])
        for unit, expected in {'us': 30.0, 'ns': 0.03, 'ms': 3e4, 's': 3e7}.items():
            with self.subTest(time_unit=unit):
                sr = self.dut.find_slew_rate(t, v, time_unit=unit)
                self.assertAlmostEqual(sr / expected, 1.0, places=9)

    def test_rc_settling_uses_10_90_average_not_peak_slope(self):
        # A bandwidth-limited (single-pole) step v = V(1 - exp(-t/tau)) has its steepest
        # slope V/tau at t = 0, but the 10-90% definition averages over the edge:
        # SR = 0.8 V / (tau ln 9). Checks the thresholds are applied to the full swing.
        V, tau = 1.2, 10e-9
        t = np.linspace(0, 40 * tau, 40001)
        v = V * (1 - np.exp(-t / tau))
        expected = 0.8 * V / (tau * np.log(9)) * 1e-6        # ~43.7 V/us
        sr = self.dut.find_slew_rate(t, v)
        self.assertAlmostEqual(sr / expected, 1.0, places=4)
        self.assertLess(sr, V / tau * 1e-6)                    # below the 120 V/us peak

    def test_pulse_train_reports_slowest_rising_edge(self):
        # Two rising edges: a fast 60 V/us edge first, then a slow 30 V/us edge after a
        # fast fall. The reported slew rate must be the worst case (30), not the first or
        # the average edge, and the fast falling edge in between must not be mistaken
        # for a rising edge.
        t = np.arange(0, 300e-9, 0.7e-9)
        v = np.interp(t, [0, 10e-9, 30e-9, 100e-9, 105e-9, 200e-9, 240e-9, 300e-9],
                         [0, 0, 1.2, 1.2, 0, 0, 1.2, 1.2])
        self.assertAlmostEqual(self.dut.find_slew_rate(t, v) / 30.0, 1.0, places=9)


if __name__ == '__main__':
    unittest.main(verbosity=2)
