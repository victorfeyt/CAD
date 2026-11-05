"""
Unit tests for CircuitEnv.action_refine.

Run FROM the CAD/ directory:
    python -m unittest unit_test_env -v
"""

import os
import unittest

import numpy as np

# CircuitEnv builds its YAML path from os.getcwd(), so make sure we're in CAD/.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from circuit_env import CircuitEnv
from unit_test_dut import load_rows, _num, REL_TOL, ABS_TOL

REF_CSV = 'references.csv'

class TestActionRefine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')

    @staticmethod
    def _parse(name, s):
        # m* params are integer multiplicities, everything else is a float
        return _num(name, s)

    def assertParamEqual(self, name, got, expected):
        # Compare in units of the parameter's step so tiny values (e.g. 4.5e-8 m)
        # are checked as strictly as large ones (e.g. 9800 ohm).
        step = self.env.param_ranges[name]['step']
        self.assertLessEqual(abs(got - expected) / step, 1e-6,
                             msg=f'{name}: got {got}, expected {expected}')

    def test_minus_one_gives_min(self):
        out = self.env.action_refine(-np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            with self.subTest(param=name):
                self.assertParamEqual(name, out[name], r['min'])

    def test_plus_one_gives_max(self):
        # The grid is [min, max) like np.arange, so the top value is one step (in the
        # parameter's own unit) below max: 24 for mp1, 2.75e-6 m for wp1, 9800 ohm for res.
        out = self.env.action_refine(np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            with self.subTest(param=name):
                self.assertParamEqual(name, out[name], r['max'] - r['step'])

    def test_zero_gives_middle(self):
        # 0 maps to the middle of the grid [min, max). With n grid points the index is
        # floor((n-1)/2), so for an even n it picks the lower of the two middle values.
        out = self.env.action_refine(np.zeros(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            n = int(round((r['max'] - r['min']) / r['step']))
            expected = r['min'] + ((n - 1) // 2) * r['step']
            with self.subTest(param=name):
                self.assertParamEqual(name, out[name], expected)

    def test_out_of_bounds_clipped(self):
        # The action_refine() docstring says it clips to [-1, 1], so test that use actions {-2, 2}
        out = self.env.action_refine(2*np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            with self.subTest(param=name):
                self.assertParamEqual(name, out[name], r['max'] - r['step'])
        out = self.env.action_refine(-2*np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            with self.subTest(param=name):
                self.assertParamEqual(name, out[name], r['min'])

    def test_matches_references_csv(self):
        # Ground truth: action_<p> in references.csv must map to param_<p>.
        rows = load_rows(REF_CSV)
        if not rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in rows:
            action = np.array([float(row[f'action_{name}']) for name in self.env.dict_params])
            out = self.env.action_refine(action)
            for name in self.env.param_ranges:
                with self.subTest(design=row['name'], param=name):
                    self.assertParamEqual(name, out[name], self._parse(name, row[name]))


class TestSimulate(unittest.TestCase):
    """Needs ngspice. Feeds each design's param_* straight into simulate() (bypassing
    action_refine) and checks every measured spec against that design's spec_* row."""

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')
        cls.rows = load_rows(REF_CSV)

    def test_matches_references_csv(self):
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            params = {name: _num(name, row[name]) for name in self.env.dict_params}
            # Reset per design: if simulate() raises, specs stays None instead of
            # holding the previous design's results.
            specs = None
            with self.subTest(design=row['name']):
                specs = self.env.simulate(params)
                self.assertEqual(set(specs), set(self.env.dict_targets))
            if specs is None:
                continue  # the failure is already recorded by the subTest above
            for name in self.env.dict_targets:
                if name not in specs:
                    continue  # already reported by the assertEqual above
                got, ref = specs[name], float(row[name])
                with self.subTest(design=row['name'], spec=name):
                    self.assertLessEqual(abs(got - ref), max(REL_TOL * abs(ref), ABS_TOL),
                                         msg=f'{name}: got {got:.6g}, ref {ref:.6g}')


class TestNormalizeSpecs(unittest.TestCase):
    """No simulator. Feeds each design's reference spec_* into normalize_specs() and
    checks the result against that design's norm_* row."""

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')
        cls.rows = load_rows(REF_CSV)

    def test_matches_references_csv(self):
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            spec_dict = {name: float(row[name]) for name in self.env.dict_targets}
            norm_specs = self.env.normalize_specs(spec_dict)
            with self.subTest(design=row['name']):
                self.assertEqual(set(norm_specs), set(self.env.dict_targets))
            for name in self.env.dict_targets:
                # Pure arithmetic on identical inputs, so only CSV rounding (12 digits)
                # separates us from the reference. Absolute tolerance, since values
                # live in [-1, 1] and can sit near 0.
                with self.subTest(design=row['name'], spec=name):
                    self.assertAlmostEqual(norm_specs[name], float(row[f'norm_{name}']),
                                           places=9, msg=name)

    def test_zero_spec_gives_minus_one(self):
        # (0 - goal) / (0 + goal) = -1 for any positive goal, the worst normalized value.
        # A negative phase margin (unstable) is clipped to 0, so it must map to -1 too.
        norm_specs = self.env.normalize_specs({name: 0.0 for name in self.env.dict_targets})
        for name in self.env.dict_targets:
            with self.subTest(spec=name):
                self.assertAlmostEqual(norm_specs[name], -1.0, places=12)
        spec_dict = {name: float(goal) for name, goal in self.env.dict_targets.items()}
        spec_dict['phm'] = -30.0
        self.assertAlmostEqual(self.env.normalize_specs(spec_dict)['phm'], -1.0, places=12)

    def test_goal_spec_gives_zero(self):
        # (goal - goal) / (goal + goal) = 0, the middle of the normalized range.
        spec_dict = {name: float(goal) for name, goal in self.env.dict_targets.items()}
        norm_specs = self.env.normalize_specs(spec_dict)
        for name in self.env.dict_targets:
            with self.subTest(spec=name):
                self.assertAlmostEqual(norm_specs[name], 0.0, places=12)

    def test_negative_phase_margin_gives_minus_one(self):
        # PM <= 0 is unstable, so normalize_specs clips it to 0 -> (0 - 60) / (0 + 60) = -1.
        spec_dict = {name: float(goal) for name, goal in self.env.dict_targets.items()}
        spec_dict['phm'] = -45.0
        self.assertAlmostEqual(self.env.normalize_specs(spec_dict)['phm'], -1.0, places=12)


class TestRewardComputation(unittest.TestCase):
    """No simulator. Feeds each design's reference norm_* straight into
    reward_computation() (bypassing normalize_specs, which TestNormalizeSpecs covers,
    so a normalization bug can't masquerade as a reward bug) and checks the result
    against that design's reward row."""

    # Specs where a higher value is unambiguously better. A negative norm on any of
    # these is a missed hard constraint, independent of how noise is handled.
    HIGHER_IS_BETTER = ('gain', 'phm', 'slewRate', 'ugbw')

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest',
                             simulator='ngspice', success_threshold=0.0)
        cls.rows = load_rows(REF_CSV)

    def _norm_specs(self, row):
        return {name: float(row[f'norm_{name}']) for name in self.env.dict_targets}

    def test_returns_reward_and_flag(self):
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            with self.subTest(design=row['name']):
                out = self.env.reward_computation(self._norm_specs(row))
                self.assertIsInstance(out, tuple)
                self.assertEqual(len(out), 2)
                reward, hard_satisfied = out
                self.assertTrue(np.isfinite(reward))
                self.assertIsInstance(hard_satisfied, (bool, np.bool_))

    def test_matches_references_csv(self):
        # Same tolerance as unit_test_dut Part B: the TA rewards are only reproducible
        # to within a few percent, so REL_TOL rather than a digit-exact comparison.
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            reward, _ = self.env.reward_computation(self._norm_specs(row))
            ref = float(row['reward'])
            with self.subTest(design=row['name']):
                self.assertAlmostEqual(reward, ref, places=9,
                                       msg=f'reward: got {reward:.6g}, ref {ref:.6g}')

    def test_hard_satisfied_flag(self):
        # A design that misses a higher-is-better hard constraint can't satisfy them all.
        if not self.rows:
            self.skipTest(f'{REF_CSV} not found')
        for row in self.rows:
            norm_specs = self._norm_specs(row)
            missed = [s for s in self.HIGHER_IS_BETTER
                      if s in self.env.hard_constraints and norm_specs[s] < 0]
            if not missed:
                continue
            _, hard_satisfied = self.env.reward_computation(norm_specs)
            with self.subTest(design=row['name']):
                self.assertFalse(hard_satisfied, msg=f'misses {missed} but flagged satisfied')


if __name__ == '__main__':
    unittest.main(verbosity=2)
