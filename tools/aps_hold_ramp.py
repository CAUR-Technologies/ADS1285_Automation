"""
Test de maintien vertical : STA puis montee de STF EN MARCHE par paliers.

Decouverte : sur l'APS 0109, STF ne s'ecrit QU'EN MARCHE (a l'arret la commande
est acquittee mais ignoree, reste a 4). Au STA l'asservissement demarre a SSS=3
(soft) -> trop faible pour tenir l'armature verticale contre la gravite -> elle
flue et trippe l'overtravel en ~1 s. Ici on monte STF tout de suite apres le STA
pour donner de l'autorite de maintien AVANT le trip.

Timeline (l'operateur suit le CLIC du relais START comme top depart) :
  t=0.0  STA  (tu entends le CLIC -> garde l'armature CENTREE a la main)
  t~0.2..1.6  montee STF par paliers (+3 toutes les 0.4 s) jusqu'a la cible
  t~2.0  >>> LACHE doucement l'armature <<<  (compte ~2 s apres le clic)
  t=2..8 on logge STA? : si True jusqu'au bout = CA TIENT.

L'operateur garde un doigt sur STOP : si l'armature OSCILLE/vibre, STF est trop
haut -> STOP, relancer avec une cible plus basse.

Usage :
    python tools/aps_hold_ramp.py                 # vertical, cible STF=12
    python tools/aps_hold_ramp.py vertical 10     # cible STF=10
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    target = max(0, min(31, target))
    hold_s = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    ott = int(sys.argv[4]) if len(sys.argv) > 4 else None   # tolerance overtravel a regler avant STA

    c = APSController(axis=axis)
    c.connect()
    if ott is not None:
        c.set_overtravel_tolerance(ott)
        print(f"[{axis}] OTT regle a {c.get_overtravel_tolerance()}")
    print(f"[{axis}] depart : STF={c.get_stiffness()} SSS={c.get_stiffness_start_value()} "
          f"OTT={c.get_overtravel_tolerance()} GES={c.get_last_error()}")

    print(">>> STA (tu vas entendre le CLIC) -- GARDE l'armature CENTREE a la main.")
    t0 = time.time()
    c.start()

    # Montee de STF par paliers de +3 (a partir de SSS=3) jusqu'a la cible.
    steps = list(range(6, target + 1, 3))
    if not steps or steps[-1] != target:
        steps.append(target)
    for s in steps:
        time.sleep(0.4)
        try:
            c.set_stiffness(s)
            print(f"  t+{time.time()-t0:4.1f}s  STF -> {c.get_stiffness():2}  STA?={c.get_start_status()}")
        except Exception as e:                       # noqa: BLE001
            print(f"  t+{time.time()-t0:4.1f}s  set STF {s} ERREUR {e}  STA?={c.get_start_status()}")

    # Phase de CAPTURE : on garde STF a la cible pendant que l'operateur tient
    # l'armature centree, le temps que l'integrateur charge le biais de gravite.
    print(f"  ... GARDE l'armature CENTREE encore ~5 s (compte lentement jusqu'a 5) ...")
    capture_end = (time.time() - t0) + 5.0
    while time.time() - t0 < capture_end:
        time.sleep(0.5)
        try:
            c.set_stiffness(target)                  # re-assert (STF redescend sinon)
            print(f"  t+{time.time()-t0:4.1f}s  capture STF={c.get_stiffness():2} STA?={c.get_start_status()}")
        except Exception:                            # noqa: BLE001
            pass
        if not c.get_start_status():
            print(f"  --> TRIP pendant la capture a t+{time.time()-t0:.1f}s")
            c.disconnect()
            return 0

    print(f"  ---> LACHE doucement l'armature MAINTENANT <---")

    # Surveillance du maintien
    held = True
    while time.time() - t0 < hold_s:
        time.sleep(0.5)
        try:
            c.set_stiffness(target)                  # re-assert en continu (sinon STF retombe a 4)
            on = c.get_start_status()
        except Exception as e:                       # noqa: BLE001
            print(f"  t+{time.time()-t0:4.1f}s  STA? ERREUR {e}")
            continue
        print(f"  t+{time.time()-t0:4.1f}s  STA?={on}  STF={c.get_stiffness()}")
        if not on:
            held = False
            print(f"  --> TRIP a t+{time.time()-t0:.1f}s (l'armature a flue hors fenetre)")
            break

    print(f"\nVERDICT : {'TIENT (STA? reste True)' if held else 'NE TIENT PAS (trip)'} "
          f"a STF cible {target}.")
    print(f"GES final : {c.get_last_error()}")
    try:
        c.stop()
    except Exception:                                # noqa: BLE001
        pass
    c.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
