"""
Test ciblé du démarrage (STA) d'un contrôleur APS 0109.

But : trancher si l'axe (vertical par défaut) démarre réellement ou reste figé
en bootloader/moniteur (« Mega64 \\r? » sur l'afficheur, problème ouvert depuis
le 2026-05-27). AUCUN signal Wavetek n'est envoyé : le servo ne fait que tenir
la position. Sûr tant que ZER est centré (0).

Séquence :
  1. lit ZER, STA?, GES (état avant)
  2. envoie STA
  3. sonde STA? toutes les 0,5 s pendant ~4 s
  4. relit GES, puis STP (laisse le contrôleur arrêté)

Surveille l'AFFICHEUR physique pendant le test : bannière figée = bootloader.

Usage : python tools/aps_sta_test.py [vertical|horizontal]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"

    c = APSController(axis=axis)
    c.connect()

    zer = c.get_zero_position()
    print(f"[{axis}] ZER (zéro) avant    : {zer}")
    if zer != 0:
        print(f"[!] ZER != 0 — STA tient une position décentrée. Centrer avant (ZER 0).")
    print(f"[{axis}] STA? avant          : {c.get_start_status()}")
    print(f"[{axis}] GES avant           : {c.get_last_error()}")

    print(f"\n>>> Envoi STA — surveille l'afficheur du 0109 {axis}...")
    c.start()

    started = False
    for i in range(8):                       # 8 × 0,5 s = 4 s
        time.sleep(0.5)
        try:
            s = c.get_start_status()
        except Exception as e:               # noqa: BLE001
            print(f"    t+{(i+1)*0.5:.1f}s : STA? ERREUR -> {e}  (contrôleur muet ?)")
            continue
        print(f"    t+{(i+1)*0.5:.1f}s : STA? = {s}")
        if s:
            started = True

    print(f"\n[{axis}] GES après           : {c.get_last_error()}")
    print(f"[{axis}] Verdict             : "
          f"{'DÉMARRE (STA? True)' if started else 'NE DÉMARRE PAS (STA? jamais True)'}")

    print(f">>> STP (arrêt)...")
    try:
        c.stop()
        print(f"[{axis}] STA? après STP      : {c.get_start_status()}")
    except Exception as e:                   # noqa: BLE001
        print(f"    STP ERREUR -> {e}")

    c.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
