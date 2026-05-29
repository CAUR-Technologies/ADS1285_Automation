"""
Diagnostic / recuperation des controleurs APS 0109 (Vertical / Horizontal).

- Lit et COMPARE toute la config des deux axes (read-only par defaut).
- Option de recuperation : RST d'un axe (remise aux defauts) puis restauration
  guidee des limites (PMA/PMI/OTT/ZER/SSS) + re-test de l'ecriture STF.

Sert notamment quand un controleur refuse une commande (ex. STF bloque a 31) :
on voit en quoi l'axe fautif differe de l'axe sain, et on tente un RST cible.

Usage :
    python tools/aps_compare.py                  # lit et compare V vs H
    python tools/aps_compare.py --read vertical   # lit un seul axe
    python tools/aps_compare.py --reset vertical  # RST + restauration (confirmation)

Le RST est fait controleur ARRETE (STP) et ne RElance PAS le controleur :
reconfigure/redemarre ensuite depuis le GUI (et reprogramme les limites avant
tout signal AC).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402

# (cle, libelle, methode getter) — ordre d'affichage
READOUTS = [
    ("fwv", "FWV  firmware",        "get_firmware_version"),
    ("ser", "SER  n_serie",         "get_serial_number"),
    ("sta", "STA  demarre",         "get_start_status"),
    ("stf", "STF  stiffness",       "get_stiffness"),
    ("sss", "SSS  stiff_depart",    "get_stiffness_start_value"),
    ("wtr", "WTR  rampe",           "get_wait_time_ramping"),
    ("zer", "ZER  zero",            "get_zero_position"),
    ("pma", "PMA  pos_max",         "get_position_max"),
    ("pmi", "PMI  pos_min",         "get_position_min"),
    ("ott", "OTT  overtravel",      "get_overtravel_tolerance"),
    ("srv", "SRV  mode_service",    "get_service_mode"),
]

# (cle, methode setter, libelle) — parametres restaures apres un RST
RESTORE = [
    ("pma", "set_position_max",        "PMA"),
    ("pmi", "set_position_min",        "PMI"),
    ("ott", "set_overtravel_tolerance", "OTT"),
    ("sss", "set_stiffness_start_value", "SSS"),
    ("zer", "set_zero_position",       "ZER"),
]


def read_config(ctrl) -> dict:
    """Lit tous les parametres ; valeur ou 'ERR: ...' par cle."""
    cfg = {}
    for key, _label, method in READOUTS:
        try:
            cfg[key] = getattr(ctrl, method)()
        except Exception as e:                      # noqa: BLE001
            cfg[key] = f"ERR: {e}"
    return cfg


def _open(axis: str) -> APSController:
    ctrl = APSController(axis=axis)
    ctrl.connect()
    return ctrl


def _fmt(v) -> str:
    return str(v)


def print_one(cfg: dict, title: str) -> None:
    print(f"\n=== {title} ===")
    for key, label, _ in READOUTS:
        print(f"  {label:18} : {_fmt(cfg.get(key, '-'))}")


def cmd_compare() -> int:
    cfgs = {}
    for axis in ("vertical", "horizontal"):
        try:
            c = _open(axis)
            cfgs[axis] = read_config(c)
            c.disconnect()
        except Exception as e:                      # noqa: BLE001
            print(f"[{axis}] connexion impossible : {e}")
            cfgs[axis] = None

    print(f"\n{'Parametre':20} | {'Vertical':16} | {'Horizontal':16} | diff")
    print("-" * 64)
    ndiff = 0
    for key, label, _ in READOUTS:
        v = cfgs["vertical"][key] if cfgs.get("vertical") else "(absent)"
        h = cfgs["horizontal"][key] if cfgs.get("horizontal") else "(absent)"
        mark = ""
        if str(v) != str(h):
            mark = "<<<"
            ndiff += 1
        print(f"{label:20} | {_fmt(v):16} | {_fmt(h):16} | {mark}")
    print("-" * 64)
    print(f"{ndiff} difference(s). Un STF/SSS qui diverge (ex. 31 vs 3) ou un "
          f"SRV different pointe l'unite/le mode fautif.")
    return 0


def cmd_read(axis: str) -> int:
    try:
        c = _open(axis)
    except Exception as e:                          # noqa: BLE001
        print(f"[{axis}] connexion impossible : {e}")
        return 1
    print_one(read_config(c), f"Config {axis}")
    c.disconnect()
    return 0


def cmd_reset(axis: str) -> int:
    try:
        c = _open(axis)
    except Exception as e:                          # noqa: BLE001
        print(f"[{axis}] connexion impossible : {e}")
        return 1

    before = read_config(c)
    print_one(before, f"Config {axis} AVANT reset")

    print(f"\n[!] RST remet l'APS 0109 [{axis}] aux defauts (perte des limites "
          f"PMA/PMI/OTT). Elles seront restaurees depuis les valeurs ci-dessus "
          f"si elles sont lisibles.")
    if input("    Confirmer le RST ? [oui/non] ").strip().lower() not in ("oui", "o", "yes", "y"):
        print("    Annule.")
        c.disconnect()
        return 0

    # Arret avant reset (pas de signal, pas de mouvement)
    try:
        c.stop()
    except Exception as e:                          # noqa: BLE001
        print(f"    STP : {e}")

    print("    Envoi RST (le controleur peut redemarrer)...")
    try:
        c.reset()
    except Exception as e:                          # noqa: BLE001
        print(f"    (reponse RST non standard — normal si reboot : {e})")

    # Le MCU peut rebooter (banniere) : on referme et rouvre proprement
    c.disconnect()
    time.sleep(2.0)
    try:
        c = _open(axis)
    except Exception as e:                          # noqa: BLE001
        print(f"    reconnexion post-RST impossible : {e}")
        return 1

    # Restauration des limites lisibles
    print("    Restauration des limites :")
    for key, setter, label in RESTORE:
        val = before.get(key)
        if isinstance(val, int):
            try:
                getattr(c, setter)(val)
                print(f"      {label} = {val} restaure")
            except Exception as e:                  # noqa: BLE001
                print(f"      {label} : echec restauration ({e})")
        else:
            print(f"      {label} : valeur d'origine illisible ({val}) — non restaure")

    # Re-test de l'ecriture STF (le but de la manoeuvre)
    try:
        c.set_stiffness(3)
        applied = c.get_stiffness()
        verdict = "OK (ecriture acceptee)" if applied == 3 else "TOUJOURS BLOQUE"
        print(f"\n    Test STF : demande 3 -> relu {applied}  => {verdict}")
    except Exception as e:                          # noqa: BLE001
        print(f"\n    Test STF impossible : {e}")

    print_one(read_config(c), f"Config {axis} APRES reset+restauration")
    print("\n    Controleur laisse ARRETE. Reconfigure/redemarre depuis le GUI ;"
          " verifie les limites avant tout signal AC.")
    c.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnostic/recuperation APS 0109 (V/H).")
    p.add_argument("--read", choices=["vertical", "horizontal"],
                   help="lire la config d'un seul axe")
    p.add_argument("--reset", choices=["vertical", "horizontal"],
                   help="RST de l'axe + restauration des limites (confirmation)")
    args = p.parse_args()
    if args.reset:
        return cmd_reset(args.reset)
    if args.read:
        return cmd_read(args.read)
    return cmd_compare()


if __name__ == "__main__":
    sys.exit(main())
