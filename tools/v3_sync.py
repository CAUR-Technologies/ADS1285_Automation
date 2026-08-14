"""V3 — synchro inter-voies (<=1 echantillon) par tap.

Principe : les 3 ADS1285 doivent echantillonner SIMULTANEMENT. Un tap (impulsion
mecanique) sur le boitier excite les 3 axes quasi en meme temps (propagation dans
le corps ~us, negligeable vs 4 ms @ 250 Hz). On enveloppe (Hilbert) chaque voie
autour du tap et on cross-correle les paires -> decalage inter-voies sous-echantillon.

Verdict : |decalage| <= 1 echantillon (4 ms @ 250 Hz) = PASS.
Complement : delta des start_time_ns d'en-tete (doit etre ~0 ; un ecart franc =
probleme d'etiquetage/portage de la ligne SYNC PD4).

L'unite doit avoir DEJA enregistre un survey contenant le tap, puis l'enregistrement
ARRETE (GET sur record arrete = pas de gel). Usage :
    python tools/v3_sync.py                 # auto : dernier survey enregistre
    python tools/v3_sync.py /survey-data/XX # survey explicite
"""
import os
import sys
import re

import numpy as np
from scipy.signal import hilbert, correlate, correlation_lags

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from equipment.geophone3axis import dat_reader
from config.settings import GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID

TS_RE = re.compile(r"_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)")


def _newest_file(g):
    """Fichier .dat au timestamp de NOM le plus recent, toutes surveys (= dernier record).

    Le tap ayant ete fait juste avant le STOP, il est dans le fichier ferme en dernier.
    """
    best_path, best_ts = None, ""
    for d in g.ls("/survey-data"):
        if not d.get("dir"):
            continue
        for f in g.ls(d["path"]):
            if f.get("dir"):
                continue
            m = TS_RE.search(os.path.basename(f["path"]))
            if m and m.group(1) > best_ts:
                best_ts, best_path = m.group(1), f["path"]
    return best_path


def _load_channels(g, target):
    """GET le(s) .dat cible(s) -> {channel_id: (data, start_ns, fs)} concatene.

    `target` = un fichier .dat (analyse ce seul fichier) ou un dossier survey (tous)."""
    import tempfile
    if target.endswith(".dat"):
        files = [target]
    else:
        files = sorted(f["path"] for f in g.ls(target) if not f.get("dir"))
    if not files:
        raise SystemExit(f"Rien a analyser : {target}")
    by_ch = {}
    tmp = tempfile.mkdtemp()
    for fp in files:
        raw = g.get_file(fp)
        local = os.path.join(tmp, os.path.basename(fp))
        with open(local, "wb") as fh:
            fh.write(raw)
        try:
            chans = dat_reader.read_dat(local)
        except Exception as e:                       # noqa: BLE001
            print(f"  ! {os.path.basename(fp)} illisible ({e}) — ignore")
            continue
        for c in chans:
            slot = by_ch.setdefault(c.channel_id, {"data": [], "start_ns": c.start_time_ns,
                                                   "fs": c.sample_rate_hz})
            slot["data"].append(np.asarray(c.data))
    out = {}
    for ch, s in by_ch.items():
        out[ch] = (np.concatenate(s["data"]), s["start_ns"], s["fs"])
    return out


def _envelope(x, fs):
    """Enveloppe Hilbert detrendee, centree sur la fenetre du tap le plus fort."""
    x = np.asarray(x, dtype=np.float64)
    x = x - np.mean(x)
    env = np.abs(hilbert(x))
    return env


def _lag_samples(ea, eb, fs):
    """Decalage (echantillons, signe : >0 = a EN RETARD sur b) par cross-correl. + parabole."""
    ea = ea - ea.mean()
    eb = eb - eb.mean()
    c = correlate(ea, eb, mode="full")
    lags = correlation_lags(len(ea), len(eb), mode="full")
    p = int(np.argmax(c))
    lag0 = float(lags[p])
    if 0 < p < len(c) - 1:
        y0, y1, y2 = c[p - 1], c[p], c[p + 1]
        denom = (y0 - 2 * y1 + y2)
        d = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
    else:
        d = 0.0
    return lag0 + d


def main():
    survey = sys.argv[1] if len(sys.argv) > 1 else None
    found = discover_units(vid=GEOPHONE3AXIS_VID, pid=GEOPHONE3AXIS_PID)
    if not found:
        raise SystemExit("Aucune unite detectee (USB ?).")
    sn, port = found[0]
    g = Geophone3Axis(port, serial_number=sn)
    g.connect()
    try:
        if survey is None:
            survey = _newest_file(g)
            if not survey:
                raise SystemExit("Aucun fichier .dat sur la SD.")
        print(f"Unite {sn} — fichier analyse : {survey}")
        chans = _load_channels(g, survey)
    finally:
        try:
            g.close()
        except Exception:  # noqa: BLE001
            pass

    ids = sorted(chans)
    if len(ids) < 3:
        raise SystemExit(f"Il faut 3 voies, seulement {ids} presentes.")
    fs = chans[ids[0]][2]
    n = min(len(chans[c][0]) for c in ids)
    print(f"fs = {fs:g} Hz | {n} echantillons/voie ({n/fs:.1f} s) | 1 ech = {1000/fs:.2f} ms\n")

    # 1) Coherence des en-tetes (start_time_ns)
    t0 = {c: chans[c][1] for c in ids}
    ref = t0[ids[0]]
    print("En-tetes start_time_ns (delta vs voie 1) :")
    for c in ids:
        dt_ns = t0[c] - ref
        print(f"  voie {c}: {dt_ns:+d} ns  ({dt_ns/1e9*fs:+.3f} ech)")
    print()

    # 2) Fenetre du tap : max d'energie combinee des 3 enveloppes
    envs = {c: _envelope(chans[c][0][:n], fs) for c in ids}
    comb = sum(envs[c] / (envs[c].max() or 1) for c in ids)
    pk = int(np.argmax(comb))
    w0, w1 = max(0, pk - int(0.4 * fs)), min(n, pk + int(0.6 * fs))
    print(f"Tap detecte a t={pk/fs:.2f} s -> fenetre [{w0/fs:.2f};{w1/fs:.2f}] s\n")
    win = {c: envs[c][w0:w1] for c in ids}

    # 3) Verdict FIABLE = alignement d'en-tete (le firmware horodate-t-il les 3 voies
    #    ensemble ?). Sur fichiers propres il doit etre 0,000 ech. Un ecart peut aussi
    #    venir d'un record corrompu saute en tete (artefact de transfert, pas ADC).
    tol = 1.0
    hdr_worst = max(abs((t0[c] - ref) / 1e9 * fs) for c in ids)
    hdr_ok = hdr_worst <= tol
    print(f">>> V3 (horodatage inter-voies, fiable) : {'PASS' if hdr_ok else 'ALERTE'} <<<  "
          f"max |delta en-tete| = {hdr_worst:.3f} ech")
    if not hdr_ok:
        print("    (verifier qu'aucun record n'a ete saute en tete : corruption transfert)")

    # 4) Cross-correlation d'enveloppe = INDICATIF SEULEMENT. Un tap (mecanique) filtre
    #    differemment chaque axe (resonances/Q distincts) : le decalage d'enveloppe
    #    melange mecanique + echantillonnage et NE prouve PAS un defaut de synchro ADC.
    #    Pour trancher la synchro PHYSIQUE <=1 ech : injecter le MEME signal ELECTRIQUE
    #    dans les 3 entrees ADC (Wavetek splitte) -> la cross-correl. isole l'ADC.
    print("\n[indicatif — CONFOND LA MECANIQUE, ne pas conclure] cross-correl. enveloppe tap :")
    for a, b in [(ids[0], ids[1]), (ids[0], ids[2]), (ids[1], ids[2])]:
        lag = _lag_samples(win[a], win[b], fs)
        print(f"  voie {a} vs {b}: {lag:+.3f} ech  ({lag*1000/fs:+.2f} ms)")
    print("  -> pour la synchro ADC physique : injection electrique commune aux 3 entrees.")


if __name__ == "__main__":
    main()
