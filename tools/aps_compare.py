"""
Diagnostic / recuperation des controleurs APS 0109 (Vertical / Horizontal).

- Lit et COMPARE toute la config RS232-accessible des deux axes (read-only par
  defaut), GES inclus (memoire de la derniere erreur).
- Option de recuperation : RST d'un axe (remise aux defauts) puis restauration
  guidee des limites (PMA/PMI/OTT/ZER/SSS) + re-test de l'ecriture STF.

Sert notamment quand un controleur refuse une commande (ex. STF bloque a 31)
ou ne sort plus de signal vers l'ampli : on voit en quoi l'axe fautif differe
de l'axe sain, on lit GES pour identifier la cause (overtravel, CRC, ...) et
on tente un RST cible.

Usage :
    python tools/aps_compare.py                  # lit et compare V vs H
    python tools/aps_compare.py --read vertical   # lit un seul axe
    python tools/aps_compare.py --reset vertical  # RST + restauration (confirmation)

Le RST est fait controleur ARRETE (STP) et ne RElance PAS le controleur :
reconfigure/redemarre ensuite depuis le GUI (et reprogramme les limites avant
tout signal AC).

Ce que cet outil NE couvre PAS — limitation materielle, pas logicielle :
le chapitre 6 du manuel APS 0109 ne documente que 24 commandes RS232. Les
13 menus de configuration (couples Overtravel limit Menus 2-7, Menu 8 TimeOut,
Menu 9 monitoring capteur, Menu 10 horizontal shaker, Menus 11-13 input/output
sockets, ...) sont accessibles UNIQUEMENT par le panneau frontal. Pour les
comparer entre V et H, les relever a la main sur chaque unite.

Note GES : per doc §6.11, la lecture de GES *vide* la memoire d'erreur. On la
lit donc en premier pour ne pas la masquer accidentellement.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController  # noqa: E402

# (cle, libelle, methode getter) — ordre d'affichage
# GES en PREMIER : sa lecture vide la memoire d'erreur cote controleur.
READOUTS = [
    ("ges", "GES  derniere_err",   "get_last_error"),
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

    print(f"\n{'Parametre':20} | {'Vertical':20} | {'Horizontal':20} | diff")
    print("-" * 72)
    ndiff = 0
    for key, label, _ in READOUTS:
        v = cfgs["vertical"][key] if cfgs.get("vertical") else "(absent)"
        h = cfgs["horizontal"][key] if cfgs.get("horizontal") else "(absent)"
        mark = ""
        if str(v) != str(h):
            mark = "<<<"
            ndiff += 1
        print(f"{label:20} | {_fmt(v):20} | {_fmt(h):20} | {mark}")
    print("-" * 72)
    print(f"{ndiff} difference(s). Un STF/SSS qui diverge (ex. 31 vs 3) ou un "
          f"SRV different pointe l'unite/le mode fautif.")
    print(
        "\nGES : 'no_error' = OK ; Overtravel_TOP/Bottom = la protection s'est "
        "declenchee (limites depassees) — l'output reste coupee tant que le "
        "controleur n'a pas etait redemarre proprement.\n"
        "Rappel : les 13 menus du panneau frontal (couples Overtravel limit, "
        "Menu 8 TimeOut, Menu 9 monitoring, Menus 11-13 sockets, ...) ne sont "
        "PAS accessibles par RS232 — les comparer a la main sur les unites."
    )
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
