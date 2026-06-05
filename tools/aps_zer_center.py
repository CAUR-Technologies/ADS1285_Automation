"""
Mesure du droop chargé + tentative de re-centrage par la consigne ZER.

Démarre le contrôleur avec OTT large (STA brut pour ne pas resserrer l'OTT),
laisse l'armature chargée se stabiliser à son creux d'équilibre, puis balaie la
consigne ZER en marquant une pause à chaque pas. L'OPÉRATEUR lit le bargraphe
« Position » du panneau 0109 et repère le ZER qui ramène l'armature au centre.
On lit aussi PMA?/PMI? pour voir s'ils trahissent la position (sinon = réglages
statiques, et seul le bargraphe compte).

⚠️ Au démarrage l'armature plonge puis récupère (OTT large). Main prête, STOP prêt.
Le contrôleur est laissé EN MARCHE à la fin (ZER remis à 0) pour la suite.

Usage :
    python tools/aps_zer_center.py                 # OTT=600, ZER 0..99
    python tools/aps_zer_center.py vertical 600 0,30,60,90,-30,-60
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    ott = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    if len(sys.argv) > 3:
        zers = [int(x) for x in sys.argv[3].split(",")]
    else:
        zers = [0, 20, 40, 60, 80, 99]

    c = APSController(axis=axis)
    c.connect()
    c.set_overtravel_tolerance(ott)
    print(f"[{axis}] OTT={c.get_overtravel_tolerance()} -- STA brut. "
          f"Armature plonge+recupere, main prete.")
    c._send_command("STA")
    # settle + STF
    t0 = time.time()
    while time.time() - t0 < 6.0:
        time.sleep(0.5)
        try:
            c.set_stiffness(4)
        except Exception:                  # noqa: BLE001
            pass
        if not c.get_start_status():
            print(f"  TRIP au demarrage (t+{time.time()-t0:.1f}s). Augmente OTT.")
            c.disconnect()
            return 1

    print(f"\n[{axis}] tenu. Baseline ZER={c.get_zero_position()} "
          f"PMA={c.get_position_max()} PMI={c.get_position_min()}")
    print("\n>>> REGARDE LE BARGRAPHE 'Position' DU PANNEAU 0109 a chaque pas <<<")
    print(f"{'ZER':>5} | {'PMA':>5} | {'PMI':>5} | STA?")
    print("-" * 32)
    for z in zers:
        try:
            c.set_zero_position(z)
        except Exception as e:             # noqa: BLE001
            print(f"{z:5} | set ZER ERREUR {e}")
            continue
        time.sleep(3.0)                    # laisse le temps de regarder le bargraphe
        on = c.get_start_status()
        print(f"{z:5} | {c.get_position_max():5} | {c.get_position_min():5} | {on}")
        if not on:
            print(f"  --> TRIP a ZER={z}. Arret du balayage.")
            break

    # Remise a 0 et on laisse tourner pour la suite
    try:
        c.set_zero_position(0)
    except Exception:                      # noqa: BLE001
        pass
    print(f"\n[{axis}] ZER remis a 0, controleur LAISSE EN MARCHE. "
          f"STA?={c.get_start_status()} GES={c.get_last_error()}")
    print("Dis-moi : a quel ZER le bargraphe etait CENTRE ? (et le sens : monte/descend)")
    c.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
