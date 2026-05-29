"""
Tests des specs geophones et du calcul de vitesse max (anti-saturation).

Lancer : python tests/test_geophones.py
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment import geophones as gp


def approx(a, b, rel=1e-2):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


def test_resonance_peak_sous_amorti():
    # HG-5VHS : zeta = 0,268 -> pic ~1,94
    assert approx(gp.resonance_peak(0.268), 1.937, rel=1e-3)
    # 1/(2 zeta sqrt(1-zeta^2)) formule exacte
    z = 0.5
    assert approx(gp.resonance_peak(z), 1.0 / (2 * z * math.sqrt(1 - z * z)))


def test_resonance_peak_amorti_pas_de_pic():
    # zeta >= 1/sqrt(2) -> reponse monotone, pas de pic (facteur 1)
    assert gp.resonance_peak(1.0 / math.sqrt(2.0)) == 1.0
    assert gp.resonance_peak(0.73) == 1.0
    assert gp.resonance_peak(1.0) == 1.0


def test_vmax_au_pic_egale_safety_fois_pleine_echelle():
    # Par construction : G * vmax * Hmax = safety * FS (sortie au pic de resonance)
    for name, (g, _f0, z, _n) in gp.GEOPHONE_SPECS.items():
        v = gp.max_safe_velocity_mps(name, 2.5, safety=0.5)
        sortie_pic = g * v * gp.resonance_peak(z)
        assert approx(sortie_pic, 0.5 * 2.5), f"{name}: {sortie_pic}"


def test_vmax_valeurs_attendues():
    # HG-5VHS (G=100,4 ; zeta=0,268) -> ~6,4 mm/s ; ST-2A (G=260) -> ~4,8 mm/s
    assert approx(gp.max_safe_velocity_mps("HG-5VHS", 2.5, 0.5), 0.00643, rel=2e-2)
    assert approx(gp.max_safe_velocity_mps("ST-2A (V)", 2.5, 0.5), 0.00481, rel=2e-2)
    # Geophone moins sensible -> vitesse permise plus grande
    assert (gp.max_safe_velocity_mps("HG-6 HB", 2.5, 0.5)
            > gp.max_safe_velocity_mps("HG-5VHS", 2.5, 0.5))


def test_vmax_geophone_inconnu_fallback():
    assert gp.max_safe_velocity_mps("inexistant", 2.5, 0.5, fallback=0.01) == 0.01


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
