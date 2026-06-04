"""
Démarrage AUTO (hands-free) d'un axe vertical, via OTT transitoire.

Problème : au STA souple, l'armature verticale plonge sous la gravité avant que
le contrôleur ne développe sa force ; la plongée dépasse OTT=50 et arme un trip
overtravel (le 0109 récupère à zéro puis coupe). On SAIT que le contrôleur a
l'autorité de revenir à zéro tout seul. Idée : OTT LARGE pendant le démarrage
(la plongée ne trippe plus) -> laisser récupérer à zéro -> RESSERRER OTT à la
valeur opérationnelle. OTT est inscriptible en marche (vérifié).

Pas de tenue manuelle, pas de SSS élevé (donc pas de risque de slam).

⚠️ Première validation SUPERVISÉE : l'armature plonge puis remonte seule. Garde
une main tout près (prête à rattraper) et le doigt sur STOP.

Usage :
    python tools/aps_vert_autostart.py                 # start_ott=500, hold_ott=50
    python tools/aps_vert_autostart.py vertical 800 50  # plongée plus profonde
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def autostart(ctrl, axis, start_ott=500, hold_ott=50, stf=4,
              settle_s=6.0, confirm_s=3.0) -> bool:
    """STA hands-free avec OTT large, récupération, puis resserrage OTT.
    Retourne True si l'axe tient à hold_ott."""
    ctrl.set_overtravel_tolerance(start_ott)
    print(f"[{axis}] OTT démarrage = {ctrl.get_overtravel_tolerance()} (large).")
    print(">>> STA hands-free -- l'armature va PLONGER puis remonter. Main prête, STOP prêt.")
    t0 = time.time()
    ctrl.start()
    # Récupération : on laisse le contrôleur ramener l'armature à zéro.
    while time.time() - t0 < settle_s:
        time.sleep(0.5)
        try:
            ctrl.set_stiffness(stf)              # STF ne prend qu'en marche
        except Exception:                        # noqa: BLE001
            pass
        on = ctrl.get_start_status()
        print(f"  t+{time.time()-t0:4.1f}s  STA?={on}  STF={ctrl.get_stiffness()}")
        if not on:
            print(f"  --> TRIP pendant la récupération (plongée > OTT {start_ott}). "
                  f"Relance avec un start_ott plus grand.")
            return False
    # Resserrage de la protection
    ctrl.set_overtravel_tolerance(hold_ott)
    print(f"[{axis}] OTT resserré à {ctrl.get_overtravel_tolerance()} (opérationnel).")
    t1 = time.time()
    while time.time() - t1 < confirm_s:
        time.sleep(0.5)
        on = ctrl.get_start_status()
        print(f"  t+{time.time()-t1:4.1f}s  STA?={on}  OTT={ctrl.get_overtravel_tolerance()}")
        if not on:
            print(f"  --> TRIP au resserrage (creux d'équilibre > {hold_ott} ?). "
                  f"Augmente hold_ott.")
            return False
    print(f"[{axis}] DÉMARRAGE AUTO RÉUSSI : tient à OTT={hold_ott}, hands-free.")
    return True


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    start_ott = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    hold_ott = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    ctrl = APSController(axis=axis)
    ctrl.connect()
    try:
        ok = autostart(ctrl, axis, start_ott=start_ott, hold_ott=hold_ott)
        print(f"\n[{axis}] STA? final={ctrl.get_start_status()}  "
              f"GES={ctrl.get_last_error()}  OTT={ctrl.get_overtravel_tolerance()}")
        if ok:
            print("Contrôleur laissé EN MARCHE (maintien). STP manuel ou via un autre outil.")
        else:
            ctrl.stop()
    finally:
        ctrl.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
