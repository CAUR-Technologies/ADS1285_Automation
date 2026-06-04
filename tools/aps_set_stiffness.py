"""
Règle la rigidité (STF) d'un APS 0109 pour tester l'autorité de maintien.

Contexte : sur l'axe vertical, la boucle d'asservissement fonctionne (le courant
ampli répond à la position) mais STF=4 est trop faible pour tenir l'armature
contre la gravité → elle flue et trippe l'overtravel. On monte STF par paliers
et on teste si l'armature TIENT au centre une fois lâchée.

Cet outil NE DÉMARRE PAS le contrôleur : il règle STF (+ SSS bas pour un
démarrage souple) puis relit. C'est l'opérateur qui presse START au panneau,
armature centrée, puis lâche pour observer.

⚠️ Monter STF augmente le gain de la boucle → risque d'oscillation si trop haut
(cf. incident « oscillation violente »). Paliers petits, doigt sur STOP.

Usage :
    python tools/aps_set_stiffness.py vertical 8       # STF=8, SSS=3 (défaut)
    python tools/aps_set_stiffness.py vertical 10 5    # STF=10, SSS=5
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage : python tools/aps_set_stiffness.py <vertical|horizontal> <STF> [SSS]")
        return 2

    axis = sys.argv[1]
    stf = int(sys.argv[2])
    sss = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    if not (0 <= stf <= 31) or not (0 <= sss <= 31):
        print("STF et SSS doivent être dans 0..31.")
        return 2
    if sss > stf:
        print(f"[!] SSS({sss}) > STF({stf}) : le démarrage serait plus raide que "
              f"le régime — garde SSS <= STF pour un démarrage souple.")

    c = APSController(axis=axis)
    c.connect()

    print(f"[{axis}] avant : STF={c.get_stiffness()}  SSS={c.get_stiffness_start_value()}  "
          f"STA?={c.get_start_status()}  GES={c.get_last_error()}")

    if c.get_start_status():
        print("[!] Contrôleur DÉMARRÉ — STF n'est pris qu'au prochain STA. "
              "Arrête (STOP) puis redémarre pour appliquer.")

    c.set_stiffness_start_value(sss)
    c.set_stiffness(stf)

    print(f"[{axis}] après : STF={c.get_stiffness()}  SSS={c.get_stiffness_start_value()}")
    print(f"\n→ Centre l'armature à la main, presse START au panneau, puis LÂCHE.")
    print(f"  Tient au centre  → STF {stf} suffit (note le courant ampli au repos).")
    print(f"  Flue/trippe      → relance avec un STF plus haut (palier +2).")
    print(f"  Oscille/vibre    → STF trop haut : STOP, redescends.")

    c.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
