"""
Tests de la corrélation 3 axes en voie STREAM (Characterize3AxisSession).

Valide la MATH de `measure_point_stream` (co-acquisition + lock-in par voie →
sensibilité) sur des sinus synthétiques, sans matériel : bench et unité mockés.

Lancer : python tests/test_characterize3axis.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.geophone3axis.session import Characterize3AxisSession

F = 10.0                     # fréquence d'excitation (Hz)
SENS_V_PER_G = 0.8           # sensibilité chaîne accéléro (V/g)
ACCEL_G = 0.1                # accélération table imposée (g)
G = 9.80665
COUNTS_PEAK = {"1": 1_000_000.0, "2": 500_000.0, "3": 200_000.0}


class _MockAccel:
    """Accéléro renvoyant un sinus pur à F, amplitude = ACCEL_G·SENS (volts)."""
    sensitivity_v_per_g = SENS_V_PER_G
    sample_rate = 1000

    def acquire_seconds(self, duration_s, sample_rate=None):
        fs = sample_rate or self.sample_rate
        n = int(fs * duration_s)
        t = np.arange(n) / fs
        ref = ACCEL_G * SENS_V_PER_G * np.sin(2 * np.pi * F * t)
        return np.vstack([ref, np.zeros(n)])   # (2 voies, N) ; ref = voie 0


class _MockUnit:
    """Unité 3 axes renvoyant 3 sinus purs à F (amplitudes COUNTS_PEAK)."""
    def stream_geo(self, duration_s, rate_hz=50):
        fs = 50.0
        n = int(fs * duration_s)
        t = np.arange(n) / fs
        chans = {ch: (amp * np.sin(2 * np.pi * F * t)).astype(np.int64)
                 for ch, amp in COUNTS_PEAK.items()}
        return fs, chans


class _MockBench:
    def __init__(self):
        self._accel = _MockAccel()
        self._ref_channel = 0


def approx(a, b, tol=2e-2):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def test_measure_point_stream_sensitivity():
    """Lock-in par voie → accel_g, vitesse table et sensibilité correctes."""
    sess = Characterize3AxisSession(_MockBench(), _MockUnit(),
                                    gnss=None, pps=None, data_dir="data/3axis")
    r = sess.measure_point_stream(F, n_cycles=10, excite=False)

    assert not r["skipped"]
    assert approx(r["accel_g"], ACCEL_G)
    exp_v = ACCEL_G * G / (2 * np.pi * F)          # v = a/(2πf)
    assert approx(r["table_velocity_mps"], exp_v)

    for ch, amp in COUNTS_PEAK.items():
        c = r["channels"][ch]
        assert approx(c["counts_peak"], amp), (ch, c["counts_peak"], amp)
        assert approx(c["sens_counts_per_g"], amp / ACCEL_G)
        assert approx(c["sens_counts_per_mps"], amp / exp_v)


def test_skipped_point_out_of_envelope():
    """Un point hors enveloppe (excite=True → set_frequency_safe skipped) remonte."""
    class _BenchSkip(_MockBench):
        def set_frequency_safe(self, freq_hz, target_g=None):
            return {"skipped": True, "note": "hors course"}
    sess = Characterize3AxisSession(_BenchSkip(), _MockUnit(), None, None, "data/3axis")
    r = sess.measure_point_stream(0.1, excite=True)
    assert r["skipped"] and r["channels"] == {}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  OK   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} tests passes")
    sys.exit(1 if failed else 0)
