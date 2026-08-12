#!/usr/bin/env python
"""
Synthèse de campagne 3 axes : agrège tous les résultats de runs
(`data/3axis/*_FIT.json`, écrits automatiquement par le GUI à la fin de chaque
balayage `.dat`) en une **fiche récap par unité** — les 3 axes (voie 1/2/3 =
X/Y/Z) avec leur fit (G0, f0, ζ, pic de résonance).

Aucun copier-coller : le GUI persiste `<run>_FIT.json` + `<run>_RESULTS.csv`,
ce script les lit. Le run le PLUS RÉCENT gagne pour un (unité, axe) donné.

Usage :
    python tools/synth_campaign.py               # scanne data/3axis
    python tools/synth_campaign.py <dossier>     # autre dossier
    python tools/synth_campaign.py --csv         # + écrit campaign_summary.csv
"""
import csv
import glob
import json
import os
import sys

CH_AXIS = {"1": "X", "2": "Y", "3": "Z"}


def _peak(zeta):
    """Facteur de pic de résonance vitesse = 1/(2ζ√(1-ζ²)) si sous-amorti."""
    if zeta is None or zeta >= 0.707 or zeta <= 0:
        return 1.0
    return 1.0 / (2 * zeta * (1 - zeta ** 2) ** 0.5)


def load_fits(folder):
    """Lit tous les _FIT.json → dict {serial: {axis_label: record}} (dernier gagne)."""
    units = {}
    for path in sorted(glob.glob(os.path.join(folder, "*_FIT.json"))):
        try:
            with open(path, encoding="utf-8") as fp:
                m = json.load(fp)
        except Exception as e:   # noqa: BLE001
            print(f"  (ignoré {os.path.basename(path)} : {e})")
            continue
        serial = m.get("serial") or "?"
        ch = str(m.get("on_axis_channel") or "")
        axis = CH_AXIS.get(ch, ch or "?")
        rec = {**m, "axis_label": axis, "file": os.path.basename(path)}
        cur = units.setdefault(serial, {}).get(axis)
        # dernier run (timestamp le plus grand) gagne
        if cur is None or (rec.get("timestamp") or "") >= (cur.get("timestamp") or ""):
            units[serial][axis] = rec
    return units


def render(units):
    if not units:
        print("Aucun résultat (_FIT.json) trouvé. Lance un balayage .dat d'abord.")
        return
    for serial in sorted(units):
        axes = units[serial]
        print(f"\n=== UNITE {serial} ===")
        print(f"  {'axe':<4}{'voie':<6}{'G0 V/(m/s)':>12}{'f0 Hz':>8}"
              f"{'zeta':>7}{'pic V/(m/s)':>13}{'gain':>6}  {'chaine':<11}{'date':<17}")
        for axis in ("X", "Y", "Z", "?"):
            r = axes.get(axis)
            if not r:
                if axis in ("X", "Y", "Z"):
                    print(f"  {axis:<4}{'-':<6}{'(non mesure)':>12}")
                continue
            fit = r.get("fit")
            ch = r.get("on_axis_channel") or "?"
            date = (r.get("timestamp") or "")[:16]
            chain = r.get("axis") or ""
            gain = r.get("gain", "")
            if fit:
                pk = _peak(fit.get("zeta"))
                print(f"  {axis:<4}ch{ch:<4}{fit['G0']:>12.1f}{fit['f0']:>8.2f}"
                      f"{fit['zeta']:>7.3f}{fit['G0']*pk:>13.0f}{gain:>6}  "
                      f"{chain:<11}{date:<17}")
            else:
                print(f"  {axis:<4}ch{ch:<4}{'(fit indispo)':>12}"
                      f"{'':>15}{gain:>6}  {chain:<11}{date:<17}")
    print()


def write_csv(units, folder):
    out = os.path.join(folder, "campaign_summary.csv")
    with open(out, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["serial", "axis", "channel", "G0_V_per_mps", "f0_hz", "zeta",
                    "peak_V_per_mps", "rms_db", "gain", "chain", "timestamp", "source"])
        for serial in sorted(units):
            for axis in ("X", "Y", "Z", "?"):
                r = units[serial].get(axis)
                if not r:
                    continue
                fit = r.get("fit") or {}
                pk = _peak(fit.get("zeta")) if fit else ""
                w.writerow([
                    serial, axis, r.get("on_axis_channel", ""),
                    f"{fit.get('G0', ''):.6g}" if fit else "",
                    f"{fit.get('f0', ''):.6g}" if fit else "",
                    f"{fit.get('zeta', ''):.6g}" if fit else "",
                    f"{fit['G0']*pk:.6g}" if fit else "",
                    f"{fit.get('rms_error_db', ''):.4g}" if fit else "",
                    r.get("gain", ""), r.get("axis", ""),
                    r.get("timestamp", ""), r.get("file", "")])
    print(f"-> {out}")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    folder = args[0] if args else "data/3axis"
    units = load_fits(folder)
    render(units)
    if "--csv" in argv:
        write_csv(units, folder)


if __name__ == "__main__":
    main(sys.argv[1:])
