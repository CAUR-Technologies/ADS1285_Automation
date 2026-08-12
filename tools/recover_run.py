#!/usr/bin/env python
"""
Récupère (ou re-corrèle) un balayage 3 axes `.dat` par SEGMENTATION du signal,
sans dépendre des sods de la GNSS de référence.

Motivation : la corrélation live du GUI (`correlate_dat_run`) aligne les `.dat`
sur les fenêtres temps-GPS (`sod_start/end`) capturées via la GNSS de référence
(ProPak). Si celle-ci perd le fix ou lague à un palier, ce point est droppé ou
désaligné → sensibilités fausses. Ici on IGNORE les sods : chaque palier de
fréquence est un tone stationnaire, on le RE-DÉTECTE dans le signal `.dat`
(lock-in glissant → plateau), puis on lock-in la voie sur la fenêtre détectée.
Seuls les timestamps PROPRES du `.dat` (horloge de l'unité) et les vitesses table
du CSV (mesurées par l'accéléro NI) sont nécessaires.

Écrit `<run>_RESULTS.csv` + `<run>_FIT.json` au format GUI (lus par synth_campaign).

Usage :
    python tools/recover_run.py                       # dernier run de data/3axis
    python tools/recover_run.py <streaming_csv>       # un run précis
"""
import csv
import datetime
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment.geophone3axis.dat_reader import read_dat, UNIT3AXIS_FULLSCALE_VPEAK_G1
from equipment.dsp import coherent_phasor_at_times, snr_db, fit_geophone_response

DATA_DIR = "data/3axis"
FS = 250.0
CH_AXIS = {"1": "X", "2": "Y", "3": "Z"}


def _latest_csv():
    csvs = [f for f in glob.glob(os.path.join(DATA_DIR, "3axis_*_g*_*.csv"))
            if "_RESULTS" not in f and "summary" not in f]
    return max(csvs, key=os.path.getmtime) if csvs else None


def _parse_name(csv_path):
    """3axis_<serial>_<axis>_g<gain>_<ts>.csv → (serial, axis, gain, ts)."""
    b = os.path.basename(csv_path)[:-4]
    m = re.match(r"3axis_(.+)_(horizontal|vertical)_g(\d+)_(\d{8}_\d{6})", b)
    if not m:
        raise ValueError(f"nom de run non reconnu : {b}")
    return m.group(1), m.group(2), int(m.group(3)), m.group(4)


def _load_channels(serial, survey):
    """Concatène les 3 voies du survey, datées en sod (horloge unité)."""
    files = sorted(glob.glob(os.path.join(DATA_DIR, f"*{survey}*{serial}*.dat")))
    chan = {"1": [], "2": [], "3": []}
    skipped = 0
    for f in files:
        for c in read_dat(f):
            skipped += (c.meta.get("file", {}) or {}).get("records_skipped", 0)
            sod0 = (c.start_time_ns / 1e9) % 86400.0
            t = sod0 + np.arange(len(c.data)) / c.sample_rate_hz
            chan.setdefault(c.channel_id, []).append((t, c.data.astype(float)))
    T, X = {}, {}
    for cid, segs in chan.items():
        if not segs:
            continue
        segs.sort(key=lambda s: s[0][0])
        T[cid] = np.concatenate([s[0] for s in segs])
        X[cid] = np.concatenate([s[1] for s in segs])
    return T, X, len(files), skipped


def _detect_window(T1, X1, fq, t_after):
    """Plateau temps du palier `fq` = région contiguë > 0,5·max autour de l'argmax
    d'un lock-in glissant (fenêtre ~ max(3 s, 8/f), pas 1 s), cherchée UNIQUEMENT
    après `t_after` (sweep haute→basse : chaque palier suit le précédent → pas de
    fenêtre qui se chevauche ni qui remonte, robuste même quand le signal BF est
    noyé dans le bruit)."""
    win = max(3.0, 8.0 / fq)
    start = max(T1[0], t_after) + win / 2
    cs = np.arange(start, T1[-1] - win / 2, 1.0)
    if len(cs) == 0:
        return None
    resp = np.array([abs(coherent_phasor_at_times(
        X1[(T1 >= c - win / 2) & (T1 <= c + win / 2)],
        T1[(T1 >= c - win / 2) & (T1 <= c + win / 2)], fq))
        if ((T1 >= c - win / 2) & (T1 <= c + win / 2)).sum() > 10 else 0.0 for c in cs])
    if resp.max() <= 0:
        return None
    i = int(resp.argmax())
    hi = resp > 0.5 * resp.max()
    a = b = i
    while a > 0 and hi[a - 1]:
        a -= 1
    while b < len(hi) - 1 and hi[b + 1]:
        b += 1
    return (cs[a] - win / 2 + 0.5, cs[b] + win / 2 - 0.5)


def recover(csv_path):
    serial, axis, gain, ts = _parse_name(csv_path)
    survey = "Bench_" + ts
    lsb_v = UNIT3AXIS_FULLSCALE_VPEAK_G1 / gain / (2 ** 31)
    rows = list(csv.DictReader(open(csv_path)))
    freqs = [float(r["freq_hz"]) for r in rows]
    vel = {float(r["freq_hz"]): float(r["table_velocity_mps"]) for r in rows}
    accel = {float(r["freq_hz"]): float(r["accel_g"]) for r in rows}

    T, X, nfiles, skipped = _load_channels(serial, survey)
    if "1" not in X:
        print(f"survey {survey}: aucune voie 1 (.dat introuvable ?)")
        return
    print(f"run {serial} {axis} g{gain} — survey {survey} : {nfiles} fichiers, "
          f"{skipped} records corrompus ignorés, voie1 {len(X['1'])} ech "
          f"({T['1'][-1]-T['1'][0]:.0f}s)")

    DAT = {"1": {}, "2": {}, "3": {}}
    print(f"\n{'f(Hz)':>7}{'v(m/s)':>9}{'ch1 V/(m/s)':>13}{'snr1':>7}"
          f"{'ch2':>8}{'ch3':>8}   fenetre")
    # Sweep haute→basse : détecter dans l'ordre décroissant, chaque fenêtre après
    # la précédente (t_after avance) → les paliers BF ne peuvent plus voler une
    # fenêtre du milieu du sweep.
    t_after = T["1"][0]
    for fq in sorted(freqs, reverse=True):
        w = _detect_window(T["1"], X["1"], fq, t_after)
        if w is None:
            print(f"{fq:>7}   (non détecté)")
            continue
        lo, hi = w
        t_after = hi
        line = f"{fq:>7}{vel[fq]:>9.5f}"
        for cid in ("1", "2", "3"):
            if cid not in X:
                continue
            tt, xx = T[cid], X[cid]
            m = (tt >= lo) & (tt <= hi)
            if m.sum() < 10:
                continue
            cp = abs(coherent_phasor_at_times(xx[m], tt[m], fq))
            s = cp * lsb_v / vel[fq] if vel[fq] > 0 else float("nan")
            DAT[cid][fq] = {"sens_v_per_mps": s,
                            "sens_counts_per_mps": cp / vel[fq] if vel[fq] > 0 else float("nan"),
                            "counts_peak": cp, "n": int(m.sum())}
            if cid == "1":
                line += f"{s:>13.1f}{snr_db(xx[m], fq, FS):>7.1f}"
            else:
                line += f"{s:>8.2f}"
        print(line + f"   [{lo-T['1'][0]:.0f},{hi-T['1'][0]:.0f}]s")

    on_axis = max(("1", "2", "3"),
                  key=lambda c: sum(d["counts_peak"] for d in DAT[c].values()) if DAT[c] else 0)
    ff = [f for f in freqs if f in DAT[on_axis]]
    ss = [DAT[on_axis][f]["sens_v_per_mps"] for f in ff]
    fit = fit_geophone_response(ff, ss) if len(ff) >= 4 else None

    print(f"\n=== FIT voie {on_axis} ({CH_AXIS.get(on_axis,'?')}) ===")
    if fit:
        z = fit["zeta"]
        pk = 1.0 / (2 * z * (1 - z ** 2) ** 0.5) if z < 0.707 else 1.0
        print(f"  G0={fit['G0']:.1f} V/(m/s)  f0={fit['f0']:.2f} Hz  zeta={fit['zeta']:.3f}  "
              f"pic x{pk:.2f}={fit['G0']*pk:.0f}  RMS={fit['rms_error_db']:.2f} dB (n={fit['n']})")
    else:
        print("  fit indisponible (< 4 points)")

    base = csv_path[:-4]
    # timestamp = celui du RUN (pas du traitement) → synth_campaign ordonne bien.
    run_iso = datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S").isoformat(timespec="seconds")
    meta = {"serial": serial, "axis": axis, "gain": gain, "on_axis_channel": on_axis,
            "timestamp": run_iso, "fit": fit, "n_freqs": len(freqs),
            "method": "segmentation"}
    with open(base + "_FIT.json", "w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=2, ensure_ascii=False)
    with open(base + "_RESULTS.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        hdr = ["freq_hz", "accel_g", "on_axis_channel"]
        for c in ("1", "2", "3"):
            hdr += [f"ch{c}_S_V_per_mps", f"ch{c}_S_cnt_per_mps", f"ch{c}_counts_pk", f"ch{c}_n"]
        w.writerow(hdr)
        for f in freqs:
            row = [f"{f:g}", f"{accel.get(f, float('nan')):.6g}", on_axis]
            for c in ("1", "2", "3"):
                d = DAT[c].get(f, {})
                row += [f"{d.get('sens_v_per_mps', float('nan')):.6g}",
                        f"{d.get('sens_counts_per_mps', float('nan')):.6g}",
                        f"{d.get('counts_peak', float('nan')):.6g}", d.get("n", "")]
            w.writerow(row)
    print(f"\n-> réécrit {os.path.basename(base)}_RESULTS.csv + _FIT.json (segmentation)")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else _latest_csv()
    if not path:
        print("aucun CSV de run trouvé dans", DATA_DIR)
    else:
        recover(path)
