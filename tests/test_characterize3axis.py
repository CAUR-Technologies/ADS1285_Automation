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


def test_correlate_gps_aligned():
    """Corrélation TEMPS-GPS : sensibilité ET phase récupérées sur deux signaux
    datés en temps GPS mais échantillonnés sur des HORLOGES DIFFÉRENTES (fs et
    instants de départ distincts) — ce que fait le banc (unité .dat vs accéléro NI)."""
    from equipment.geophone3axis.dat_reader import Channel3Axis
    F, SENS_V_PER_G, G = 8.0, 0.8, 9.80665
    lsb_v = 2.048 / 1 / (2 ** 31)
    ACCEL_G = 0.05
    vel = ACCEL_G * G / (2 * np.pi * F)
    COUNTS_PK = 1.5e6
    PH_UNIT, PH_REF = np.deg2rad(30.0), np.deg2rad(-10.0)   # phases vs GPS t=0

    sod0 = 45000.0
    t_end = sod0 + 10.0
    # Référence NI : fs 500 Hz, départ sod0.
    tr = sod0 + np.arange(int((t_end - sod0) * 500.0)) / 500.0
    ref = ACCEL_G * SENS_V_PER_G * np.sin(2 * np.pi * F * tr + PH_REF)   # volts
    # Unité : fs 250 Hz, départ décalé de 0,137 s (horloge différente).
    u0 = sod0 + 0.137
    tu = u0 + np.arange(int((t_end - u0) * 250.0)) / 250.0
    counts = (COUNTS_PK * np.sin(2 * np.pi * F * tu + PH_UNIT)).astype(np.int64)
    ch = Channel3Axis(channel_id="1", data=counts,
                      start_time_ns=int(u0 * 1e9), sample_rate_hz=250.0)

    sess = Characterize3AxisSession.__new__(Characterize3AxisSession)  # sans matériel
    schedule = [{"freq_hz": F, "sod_start": sod0 + 0.5, "sod_end": t_end - 0.5}]
    res = sess.correlate(schedule, ref, tr, sens_v_per_g=SENS_V_PER_G, lsb_v=lsb_v,
                         unit_channels=[ch])
    r = res["1"][F]
    assert approx(r["accel_g"], ACCEL_G, tol=0.03), r["accel_g"]
    assert approx(r["sens_counts_per_mps"], COUNTS_PK / vel, tol=0.03)
    assert approx(r["sens_v_per_mps"], COUNTS_PK * lsb_v / vel, tol=0.03)
    exp_phase = np.rad2deg(PH_UNIT - PH_REF)   # = 40°, le -π/2 des sinus s'annule
    assert abs(r["phase_deg"] - exp_phase) < 2.0, (r["phase_deg"], exp_phase)


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
