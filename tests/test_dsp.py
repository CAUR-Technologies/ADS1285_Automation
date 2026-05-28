"""
Tests des primitives DSP (détection cohérente, SNR, THD).

Lancer : python tests/test_dsp.py
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment import dsp


def approx(a, b, tol=1e-2):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def test_amplitude_propre():
    fs, f, N = 1000, 10.0, 2000
    t = np.arange(N) / fs
    x = 3.0 * np.sin(2 * np.pi * f * t)
    assert approx(dsp.coherent_amplitude_peak(x, f, fs), 3.0)


def test_amplitude_sous_bruit():
    rng = np.random.default_rng(0)
    fs, f, N = 1000, 5.0, 40000
    t = np.arange(N) / fs
    # Signal 0.5 crête noyé sous un bruit d'écart-type 3.0 (SNR très négatif).
    # N élevé -> la variance de l'estimateur cohérent diminue en 1/sqrt(N).
    x = 0.5 * np.sin(2 * np.pi * f * t) + 3.0 * rng.standard_normal(N)
    assert approx(dsp.coherent_amplitude_peak(x, f, fs), 0.5, tol=0.1)


def test_phase():
    fs, f, N = 2000, 20.0, 4000
    t = np.arange(N) / fs
    phi = np.pi / 3
    # cos(wt + phi) = sin(wt + phi + pi/2)
    x = 2.0 * np.cos(2 * np.pi * f * t + phi)
    ph = dsp.coherent_phasor(x, f, fs)
    assert approx(abs(ph), 2.0)
    # Différence de phase entre deux signaux décalés
    y = 2.0 * np.cos(2 * np.pi * f * t + phi + np.pi / 2)
    dphase = np.angle(dsp.coherent_phasor(y, f, fs) /
                      dsp.coherent_phasor(x, f, fs))
    assert approx(dphase, np.pi / 2, tol=0.02)


def test_rms():
    fs, f, N = 1000, 10.0, 3000
    t = np.arange(N) / fs
    x = 2.0 * np.sin(2 * np.pi * f * t)  # crête 2 -> RMS 2/sqrt2
    assert approx(dsp.rms(x), 2.0 / np.sqrt(2))


def test_snr_propre_vs_bruite():
    rng = np.random.default_rng(1)
    fs, f, N = 1000, 10.0, 4000
    t = np.arange(N) / fs
    clean = np.sin(2 * np.pi * f * t)
    assert dsp.snr_db(clean, f, fs) > 60        # quasi pur
    noisy = clean + 0.1 * rng.standard_normal(N)
    snr = dsp.snr_db(noisy, f, fs)
    assert 10 < snr < 30                         # ~17 dB attendu


def test_thd():
    fs, f, N = 4000, 50.0, 8000
    t = np.arange(N) / fs
    # fondamental 1.0 + 2e harmonique 0.1 (THD = 10%)
    x = np.sin(2 * np.pi * f * t) + 0.1 * np.sin(2 * np.pi * 2 * f * t)
    assert approx(dsp.thd_percent(x, f, fs), 10.0, tol=0.05)
    # signal pur -> THD ~ 0
    pur = np.sin(2 * np.pi * f * t)
    assert dsp.thd_percent(pur, f, fs) < 0.5


def test_ratio_db():
    assert approx(dsp.ratio_db(2.0, 1.0), 6.0206, tol=1e-3)   # x2 -> +6 dB
    assert approx(dsp.ratio_db(1.0, 1.0), 0.0, tol=1e-9)
    assert dsp.ratio_db(0.0, 1.0) == float("-inf")


def test_linearity_error_db():
    # sensibilités quasi constantes -> erreur faible
    assert dsp.linearity_error_db([100.0, 101.0, 99.5]) < 0.2
    # facteur 2 d'écart -> ~6 dB
    assert approx(dsp.linearity_error_db([100.0, 200.0]), 6.0206, tol=1e-3)
    # cas dégénéré
    assert dsp.linearity_error_db([100.0]) == 0.0
    assert dsp.linearity_error_db([]) == 0.0


def test_velocity_sensitivity():
    # S_v = S_g · 2πf / g  ; à f donné, conversion exacte
    f = np.array([1.0, 10.0, 100.0])
    sg = np.array([2.0, 2.0, 2.0])
    sv = dsp.velocity_sensitivity(sg, f)
    expected = sg * 2 * np.pi * f / 9.80665
    assert np.allclose(sv, expected)


def test_fit_geophone_response_roundtrip():
    # Synthétise une réponse géophone connue, ajoute un peu de bruit, ré-ajuste.
    f = np.logspace(-1, 2, 25)  # 0.1 .. 100 Hz
    G0, f0, zeta = 5.0e5, 4.5, 0.6
    sv = dsp.geophone_velocity_response(f, G0, f0, zeta)
    rng = np.random.default_rng(0)
    sv_noisy = sv * (1.0 + 0.02 * rng.standard_normal(len(f)))  # 2% de bruit
    fit = dsp.fit_geophone_response(f, sv_noisy)
    assert fit is not None
    assert approx(fit["f0"], f0, tol=0.05)
    assert approx(fit["zeta"], zeta, tol=0.10)
    assert approx(fit["G0"], G0, tol=0.05)
    assert fit["rms_error_db"] < 1.0


def test_fit_geophone_response_too_few_points():
    assert dsp.fit_geophone_response([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) is None


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
