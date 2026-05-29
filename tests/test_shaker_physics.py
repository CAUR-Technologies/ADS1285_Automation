"""
Tests des fonctions physiques du shaker (sans materiel).

Lancer : python -m pytest tests/test_shaker_physics.py -v
     ou : python tests/test_shaker_physics.py
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import shaker_physics as sp

STROKE = 38.0  # APS 113


def approx(a, b, rel=1e-3):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


def test_envelope_basse_frequence():
    # A 0,1 Hz pour S_max=38mm, l'enveloppe vaut ~0,00153 g (doc CLAUDE.md)
    a = sp.max_accel_g(0.1, STROKE)
    assert approx(a, 0.00153, rel=0.02), f"attendu ~0.00153 g, obtenu {a:.6f}"


def test_envelope_atteint_1g_vers_2_6Hz():
    # L'enveloppe franchit 1 g aux alentours de 2,55-2,6 Hz
    f = sp.lowest_freq_for_accel(1.0, STROKE)
    assert approx(f, 2.557, rel=0.01), f"attendu ~2.56 Hz, obtenu {f:.3f}"
    assert sp.max_accel_g(f, STROKE) >= 1.0 - 1e-9


def test_deplacement_inverse_carre_frequence():
    # Doubler la frequence -> deplacement /4 pour meme acceleration
    A1 = sp.peak_displacement_mm(0.1, 5.0)
    A2 = sp.peak_displacement_mm(0.1, 10.0)
    assert approx(A1 / A2, 4.0, rel=1e-6)


def test_valeurs_doc_deplacement():
    # Table du document : 1g a differentes frequences
    # 1 Hz -> ~25 mm, 5 Hz -> ~1 mm, 10 Hz -> ~0,25 mm
    assert approx(sp.peak_displacement_mm(1.0, 1.0), 248.5, rel=0.01)
    assert approx(sp.peak_displacement_mm(1.0, 5.0), 9.94, rel=0.01)
    assert approx(sp.peak_displacement_mm(1.0, 10.0), 2.485, rel=0.01)


def test_target_plafonnee():
    # En haute frequence, target plafonne a accel_cap_g
    t = sp.target_accel_g(50.0, STROKE, fraction=0.6, accel_cap_g=1.0)
    assert approx(t, 1.0)
    # En tres basse frequence, target = fraction * enveloppe (non plafonne)
    t = sp.target_accel_g(0.1, STROKE, fraction=0.6, accel_cap_g=1.0)
    assert approx(t, 0.6 * sp.max_accel_g(0.1, STROKE))


def test_target_equivaut_deplacement_constant():
    # Tant que non plafonne, fraction constante d'enveloppe = deplacement constant
    f1, f2 = 0.2, 0.5
    t1 = sp.target_accel_g(f1, STROKE, fraction=0.6, accel_cap_g=999)
    t2 = sp.target_accel_g(f2, STROKE, fraction=0.6, accel_cap_g=999)
    A1 = sp.peak_displacement_mm(t1, f1)
    A2 = sp.peak_displacement_mm(t2, f2)
    assert approx(A1, A2, rel=1e-6)
    assert approx(A1, 0.6 * STROKE, rel=1e-6)


def test_is_safe_et_marge():
    # A 1 Hz, 0,1 g -> ~24,8 mm crete, marge ~13,2 mm (doc)
    assert sp.is_safe(1.0, 0.1, STROKE)
    m = sp.safety_margin_mm(1.0, 0.1, STROKE)
    assert approx(m, 13.15, rel=0.02), f"marge attendue ~13,2 mm, obtenue {m:.2f}"
    # Avec un offset ZER, la marge diminue
    m0 = sp.safety_margin_mm(1.0, 0.1, STROKE, zer_offset_mm=5.0)
    assert approx(m0, m - 5.0, rel=1e-6)


def test_is_safe_overtravel():
    # 0,1 Hz a 0,01 g depasse largement la course (deplacement ~1,6 m)
    assert not sp.is_safe(0.1, 0.01, STROKE)
    assert sp.safety_margin_mm(0.1, 0.01, STROKE) < 0


def test_peak_velocity_mps():
    # v = a / (2.pi.f) ; pour a=1g a 1 Hz -> 9,80665/(2pi) ≈ 1,561 m/s
    assert approx(sp.peak_velocity_mps(1.0, 1.0), 9.80665 / (2 * math.pi), rel=1e-9)


def test_max_accel_from_velocity_inverse():
    # max_accel_from_velocity_g et peak_velocity_mps sont inverses l'un de l'autre
    a = sp.max_accel_from_velocity_g(2.0, 0.01)
    assert approx(sp.peak_velocity_mps(a, 2.0), 0.01, rel=1e-9)


def test_target_limite_vitesse():
    vmax = 0.01
    # Avec limite de vitesse, la cible est plus restrictive (ou egale)
    sans = sp.target_accel_g(1.0, STROKE, fraction=0.6, accel_cap_g=1.0)
    avec = sp.target_accel_g(1.0, STROKE, fraction=0.6, accel_cap_g=1.0,
                             v_max_mps=vmax)
    assert avec <= sans + 1e-12
    # Dans la region limitee par la vitesse, la vitesse crete = vmax (constante)
    for f in (0.5, 1.0, 5.0, 20.0):
        t = sp.target_accel_g(f, STROKE, fraction=0.6, accel_cap_g=1.0,
                              v_max_mps=vmax)
        assert sp.peak_velocity_mps(t, f) <= vmax + 1e-9


def test_stiffness_bandes():
    # Bareme abaisse (STF>=10 annulait la vibration sur le banc)
    assert sp.stiffness_for_freq(0.5) == 3
    assert sp.stiffness_for_freq(1.0) == 3
    assert sp.stiffness_for_freq(9.9) == 3
    assert sp.stiffness_for_freq(10.0) == 5
    assert sp.stiffness_for_freq(49.9) == 5
    assert sp.stiffness_for_freq(50.0) == 8
    assert sp.stiffness_for_freq(100.0) == 8


def test_stiffness_schedule_configurable():
    # Bareme custom (ex. axe vertical) : f<5 -> 2, 5<=f<30 -> 4, sinon 6
    sched = [(5.0, 2), (30.0, 4), (float("inf"), 6)]
    assert sp.stiffness_for_freq(1.0, sched) == 2
    assert sp.stiffness_for_freq(5.0, sched) == 4
    assert sp.stiffness_for_freq(29.9, sched) == 4
    assert sp.stiffness_for_freq(30.0, sched) == 6
    assert sp.stiffness_for_freq(100.0, sched) == 6
    # schedule None -> bareme par defaut
    assert sp.stiffness_for_freq(1.0, None) == 3


def test_conversion_volts_g():
    # Silicon Designs 2240-005 : 800 mV/g
    assert approx(sp.accel_to_volts(1.0, 0.8), 0.8)
    assert approx(sp.volts_to_accel_g(0.8, 0.8), 1.0)
    # 0,0015 g -> 1,2 mV (proche du bruit NI -> detection coherente requise)
    assert approx(sp.accel_to_volts(0.0015, 0.8), 0.0012)


if __name__ == "__main__":
    # Execution directe sans pytest
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
