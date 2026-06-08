"""
Cherche l'OTT qui tient l'armature CHARGÉE (support géophone monté), démarrage tenu.

Contourne le start() intégré (qui resserre OTT à la valeur config 50) en envoyant
un STA brut, pour garder l'OTT qu'on veut tester. L'opérateur tient l'armature
centrée pendant le démarrage (pas de plongée), puis lâche ; on regarde si ça tient
à l'OTT donné.

But : déterminer si l'armature chargée est tenable et à quel OTT (le poids ajouté
augmente le droop -> il faut plus d'OTT qu'à vide). Si même un OTT large ne tient
pas, l'autorité de l'ampli (déjà au max) est insuffisante pour cette masse.

⚠️ Armature plus lourde : tiens fermement. Doigt sur STOP, main prête.

Usage :
    python tools/aps_load_hold.py                 # OTT=600, maintien 30s
    python tools/aps_load_hold.py vertical 300 30 # OTT=300
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    ott = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    hold_s = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    stf = int(sys.argv[4]) if len(sys.argv) > 4 else 4

    c = APSController(axis=axis)
    c.connect()
    c.set_overtravel_tolerance(ott)
    # Forcer la rigidité cible AVANT le STA : SSS=stf (démarre à stf) + STF=stf
    # (sinon l'actif relaxe vers la valeur stockée). Réasserté ensuite en continu.
    try:
        c.set_stiffness_start_value(stf)
        c.set_stiffness(stf)
    except Exception as e:                 # noqa: BLE001
        print(f"  réglage stiffness initial : {e}")
    print(f"[{axis}] OTT testé = {c.get_overtravel_tolerance()}, "
          f"SSS={c.get_stiffness_start_value()} STF={c.get_stiffness()} (cible {stf})")
    print(">>> STA brut (CLIC) -- TIENS l'armature chargée CENTREE, compte jusqu'a 5.")
    t0 = time.time()
    c._send_command("STA")                 # STA brut : NE PAS resserrer l'OTT
    # Capture : opérateur tient centré, on installe STF
    while time.time() - t0 < 6.0:
        time.sleep(0.5)
        try:
            c.set_stiffness(stf)
        except Exception:                  # noqa: BLE001
            pass
        if not c.get_start_status():
            print(f"  TRIP pendant le maintien tenu (t+{time.time()-t0:.1f}s) a OTT={ott}.")
            _finish(c)
            return 1
    print("  --> LACHE doucement l'armature. Surveillance du maintien...")
    held = True
    while time.time() - t0 < 6.0 + hold_s:
        time.sleep(0.5)
        try:
            c.set_stiffness(stf)           # réasserter (sinon relaxe vers la valeur stockée)
        except Exception:                  # noqa: BLE001
            pass
        on = c.get_start_status()
        print(f"  t+{time.time()-t0:4.1f}s  STA?={on}  OTT={c.get_overtravel_tolerance()}  STF={c.get_stiffness()}")
        if not on:
            held = False
            print(f"  --> TRIP a t+{time.time()-t0:.1f}s (droop chargé > OTT {ott}).")
            break
    print(f"\nVERDICT : {'TIENT' if held else 'NE TIENT PAS'} a OTT={ott} (armature chargée).")
    _finish(c)
    return 0


def _finish(c):
    print(f"[{c.axis}] GES={c.get_last_error()}")
    try:
        c.stop()
    except Exception:                      # noqa: BLE001
        pass
    c.disconnect()


if __name__ == "__main__":
    sys.exit(main())
