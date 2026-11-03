import time
import numpy as np
import os
import scipy.interpolate as interp
import scipy.optimize as sciopt
from scipy.optimize import differential_evolution
from .area_estimation import BPTM45nmAreaEstimator
from .ngspice_wrapper import NgspiceWrapper


class DUT(NgspiceWrapper):
    def measure_metrics(self):
        self.parse_outputs()
        spec_dict = {}
        # post process raw data
        area_estimator = BPTM45nmAreaEstimator(self.circuit_params, self.circuit_multipliers)
        spec_dict['area'] = area_estimator.find_area()
        spec_dict['current'] = self.current
        spec_dict['gain'] = self.find_dc_gain(self.vout_complex)
        spec_dict['noise'] = self.noise
        spec_dict['phm'] = self.find_phm(self.freq, self.vout_complex)
        spec_dict['slewRate'] = self.find_slew_rate(self.time, self.vout_tran, threshold_low=0.1, threshold_high=0.9, time_unit='us')
        spec_dict['ugbw'] = self.find_ugbw(self.freq, self.vout_complex)

        return spec_dict
    
    def parse_outputs(self):
        tran_fname = os.path.join(self.output_files_folder, 'tran_'+self.random_name+'.csv')
        ac_fname = os.path.join(self.output_files_folder, 'ac_'+self.random_name+'.csv')
        dc_fname = os.path.join(self.output_files_folder, 'dc_'+self.random_name+'.csv')
        noise_fname = os.path.join(self.output_files_folder, 'noise_'+self.random_name+'.csv')
        # add these file names in a list
        self.output_files = [tran_fname, ac_fname, dc_fname, noise_fname]
        for file in self.output_files:
            if not os.path.isfile(file):
                print(f"{file} doesn't exist")
        tran_raw_outputs = np.genfromtxt(tran_fname, skip_header=1)
        ac_raw_outputs = np.genfromtxt(ac_fname, skip_header=1)
        dc_raw_outputs = np.genfromtxt(dc_fname, skip_header=1)
        noise_raw_outputs = np.genfromtxt(noise_fname, skip_header=1)

        self.time = tran_raw_outputs[:, 0]
        self.vout_tran = tran_raw_outputs[:, 1]
        
        self.freq = ac_raw_outputs[:, 0]
        vout_real = ac_raw_outputs[:, 1]
        vout_imag = ac_raw_outputs[:, 2]
        self.vout_complex = vout_real + 1j*vout_imag
        
        self.current = - dc_raw_outputs[1]

        self.noise = noise_raw_outputs[0]

    # The absolute value of the complex vout at 0 frequency, so first line in csv file
    def find_dc_gain(self, vout):

        return abs(vout[0])
        
    def find_ugbw(self, freq, vout):
        # gain plot
        gain = np.abs(vout)

        # x-vector are the frequecy sample points, y vector is the gain, find value where gain crosses val = 1
        log_ugbw, valid = self._get_best_crossing(np.log10(freq), gain, 1)

        if not valid:  
            return 0.0
        return 10 ** log_ugbw   # back from log10(f) to Hz
    
    def find_phm(self, freq, vout):
        """
        Phase margin: PM = 180 + phase(f_UGBW), in degrees.
        """
        ugbw = self.find_ugbw(freq, vout)
        if ugbw == 0:   # no UGBW -> no meaningful PM, return a clearly failing value
            return -180.0

        # phase in degrees, unwrapped to remove the 360 deg jumps of np.angle
        # np.angle only returns values (-180°, 180°], by unwrapping this is corrected
        phase = np.degrees(np.unwrap(np.angle(vout)))
        phase -= phase[0]   # reference to DC phase (0 deg), just a shift to 0° at DC

        # phase at exactly f = UGBW, interpolated on the log-frequency axis
        phase_at_ugbw = np.interp(np.log10(ugbw), np.log10(freq), phase)

        return 180.0 + phase_at_ugbw
    
    def find_slew_rate(self, time, signal, threshold_low=0.1, threshold_high=0.9, time_unit='us'):
        # --- Step 1: turn the fractions into voltage levels ---
        vmin, vmax = np.min(signal), np.max(signal)
        swing = vmax - vmin
        if swing <= 1e-6:          # output doesn't move -> no slew rate
            return 0.0
        v_low  = vmin + threshold_low  * swing    # 10% level
        v_high = vmin + threshold_high * swing    # 90% level

        # --- Step 2: helper that finds the exact times the signal crosses a level ---
        def crossings(level, rising):
            above = signal >= level                           # True/False per sample
            if rising:   # sample i below, sample i+1 above
                idx = np.where(above[1:] & ~above[:-1])[0]
            else:        # sample i above, sample i+1 below
                idx = np.where(~above[1:] & above[:-1])[0]
            t0, t1 = time[idx], time[idx + 1]
            y0, y1 = signal[idx], signal[idx + 1]
            return t0 + (level - y0) * (t1 - t0) / (y1 - y0)  # linear interpolation
        
        # --- Step 3: measure every rising and falling edge ---
        slew_rates = []
        for rising, (start_level, end_level) in [(True,  (v_low,  v_high)),    # rising:  10% -> 90%
                                                (False, (v_high, v_low))]:    # falling: 90% -> 10%
            t_starts = crossings(start_level, rising)
            t_ends   = crossings(end_level,   rising)
            for t_start in t_starts:
                later = t_ends[t_ends > t_start]          # first end-crossing after this start
                if later.size:
                    slew_rates.append((v_high - v_low) / (later[0] - t_start))   # V/s

        # --- Step 4: worst case, converted to V/us ---
        units = {'s': 1.0, 'ms': 1e-3, 'us': 1e-6, 'ns': 1e-9}
        if not slew_rates:
            return 0.0
        return min(slew_rates) * units[time_unit]

    def _get_best_crossing(cls, xvec, yvec, val):
        interp_fun = interp.InterpolatedUnivariateSpline(xvec, yvec)

        def fzero(x):
            return interp_fun(x) - val

        xstart, xstop = xvec[0], xvec[-1]
        try:
            return sciopt.brentq(fzero, xstart, xstop), True
        except ValueError:
            return xstop, False
