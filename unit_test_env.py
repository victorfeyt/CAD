"""
Unit tests for CircuitEnv.action_refine.
Non for simulate

Run FROM the CAD/ directory:
    python -m unittest unit_test_env -v
"""

import os
import unittest

import numpy as np

# CircuitEnv builds its YAML path from os.getcwd(), so make sure we're in CAD/.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from circuit_env import CircuitEnv


class TestActionRefine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')

    def test_minus_one_gives_min(self):
        out = self.env.action_refine(-np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            self.assertAlmostEqual(out[name], r['min'], msg=name)

    def test_plus_one_gives_max(self):
        out = self.env.action_refine(np.ones(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            self.assertAlmostEqual(out[name], r['max'], msg=name)

    def test_zero_gives_midpoint(self):
        out = self.env.action_refine(np.zeros(self.env.n_actions))
        for name, r in self.env.param_ranges.items():
            expected = (r['min'] + r['max']) / 2
            # Snapping may move the value off the exact midpoint by at most half a step.
            # Compare in units of `step` so tiny values (e.g. 1e-7 m) are checked meaningfully.
            dist_in_steps = abs(out[name] - expected) / r['step']
            self.assertLessEqual(dist_in_steps, 0.5 + 1e-9, msg=name)
            # The result must land on the grid min, min+step, min+2*step, ...
            n_steps = (out[name] - r['min']) / r['step']
            self.assertAlmostEqual(n_steps, round(n_steps), places=6, msg=name)

    def test_out_of_range_is_clipped(self):
        out = self.env.action_refine(np.full(self.env.n_actions, 10.0))
        for name, r in self.env.param_ranges.items():
            self.assertAlmostEqual(out[name], r['max'], msg=name)


class TestSimulate(unittest.TestCase):
    """Needs ngspice installed."""

    def test_simulate_returns_dict(self):
        env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')
        params = env.action_refine(np.zeros(env.n_actions))   # midpoint design
        specs = env.simulate(params)
        self.assertIsInstance(specs, dict)

class TestNormalizeSpecs(unittest.TestCase):

    def test_normalize_specs(self):
        env = CircuitEnv(circuit_name='TwoStage', run_id='unittest', simulator='ngspice')
        spec_dict = {
            'area': 1e-12,
            'current': 1e-3,
            'gain': 100.0,
            'noise': 1e-9,
            'phm': 60.0,
            'slewRate': 1e6,
            'ugbw': 1e5
        }
        norm_specs = env.normalize_specs(spec_dict)
        for name, value in norm_specs.items():
            self.assertTrue(-1.0 <= value <= 1.0, msg=name)

if __name__ == '__main__':
    unittest.main(verbosity=2)
