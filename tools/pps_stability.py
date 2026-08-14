"""V5 — stabilite horloge / discipline 1PPS, mesuree depuis les horodatages .dat.

Le firmware horodate CHAQUE echantillon par une lecture RTC
(`sensors_data_gatherer_impl.cc` -> `rtc->getUtcDate().nanoseconds_since_epoch`),
et la RTC est **disciplinee par le 1PPS aux frontieres de seconde**
(`caur_gnss_quectel.cc`). Donc l'horodatage de debut de chaque record est une
lecture RTC independante : leur regularite mesure directement la discipline PPS.

On analyse, pour une voie, la suite des (compteur d'echantillons cumule -> start_ns) :
  * **Regression** start_ns = a + b * n_cumule  ->  b = periode d'echantillon REELLE
    en secondes UTC ; ecart a 1/fs = **erreur de frequence** ADC vs temps GPS (ppm).
    Sur un run PPS-discipline, pas de derive cumulee (l'ancrage suit l'UTC).
  * **Residus** (start_ns - droite) = **gigue d'horodatage** : quantification LSE
    (~30 us a 32768 Hz) + latence ISR + gigue de discipline PPS. RMS = plancher de
    precision (explique le bruit de TIME-05).
  * **Sauts** : delta record-a-record tres loin du nominal = correction/resync brutale.

Usage :
    python tools/pps_stability.py                 # dernier .dat enregistre
    python tools/pps_stability.py /survey-data/XX/....dat
"""
import os
import sys
import re
import struct
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from equipment.geophone3axis import dat_reader
from config.settings import GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID

TS_RE = re.compile(r"_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)")


def _newest_file(g):
    best, ts = None, ""
    for d in g.ls("/survey-data"):
        if not d.get("dir"):
            continue
        for f in g.ls(d["path"]):
            if f.get("dir"):
                continue
            m = TS_RE.search(os.path.basename(f["path"]))
            if m and m.group(1) > ts:
                ts, best = m.group(1), f["path"]
    return best


def _records_from_bytes(raw, want_ch=None):
    """Itere les records d'un buffer -> (want_ch, [(start_ns,numSamples,fs)], clean).

    `clean` = True si tout le fichier a ete parse sans record corrompu. La corruption
    CDC (finance #6) tue le generateur simplemseed au 1er record casse -> on garde
    les bons records avant."""
    import io
    import simplemseed
    from simplemseed.mseed3 import Miniseed3Exception
    try:
        from simplemseed.exceptions import CodecException
    except ImportError:
        from simplemseed import CodecException
    CORRUPT = (Miniseed3Exception, CodecException, UnicodeDecodeError, struct.error, ValueError)
    recs = []
    clean = True
    it = simplemseed.readMSeed3Records(io.BytesIO(raw))
    while True:
        try:
            rec = next(it)
            caur = dat_reader._caurtech(rec)
            if rec.header.numSamples == 0:
                continue
            ch = str(caur.get("channel") or "1")
            if want_ch is None:
                want_ch = ch
            if ch != want_ch:
                continue
            recs.append((dat_reader._start_ns(rec), int(rec.header.numSamples),
                         float(rec.header.sampleRate)))
        except StopIteration:
            break
        except CORRUPT:
            clean = False
            break
    recs.sort(key=lambda r: r[0])
    return want_ch, recs, clean


def _get_most_complete(g, path, tries=8):
    """GET repete : la corruption CDC tronque a une position ALEATOIRE a chaque
    transfert -> on garde celui qui donne le plus de records (ou le 1er 100% propre)."""
    best, best_n, clean_hit = None, -1, False
    for i in range(tries):
        _, recs, clean = _records_from_bytes(g.get_file(path))
        n = len(recs)
        print(f"  GET #{i+1}: {n} records{' (propre)' if clean else ' (tronque en transit)'}")
        if n > best_n:
            best, best_n = recs, n
        if clean:
            clean_hit = True
            break
    return best, clean_hit


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    found = discover_units(vid=GEOPHONE3AXIS_VID, pid=GEOPHONE3AXIS_PID)
    if not found:
        raise SystemExit("Aucune unite detectee (USB ?).")
    sn, port = found[0]
    g = Geophone3Axis(port, serial_number=sn)
    g.connect()
    try:
        if target is None:
            target = _newest_file(g)
            if not target:
                raise SystemExit("Aucun .dat sur la SD.")
        print(f"Unite {sn} — fichier : {target}")
        print("GET (transfert robuste — la corruption CDC tronque au hasard) :")
        recs, clean = _get_most_complete(g, target)
    finally:
        try:
            g.close()
        except Exception:  # noqa: BLE001
            pass

    if not recs or len(recs) < 3:
        raise SystemExit(f"Pas assez de records ({len(recs) if recs else 0}) — "
                         "enregistre plus longtemps ou relance (transfert).")
    ch = "1"
    print(f"  -> {len(recs)} records retenus"
          + ("" if clean else " (meilleur transfert ; fin possiblement tronquee)") + "\n")
    start = np.array([r[0] for r in recs], dtype=np.float64)   # ns
    nsamp = np.array([r[1] for r in recs], dtype=np.float64)
    fs = recs[0][2]
    dur_s = (start[-1] - start[0]) / 1e9
    print(f"voie {ch} | {len(recs)} records | fs nominal = {fs:g} Hz | "
          f"{int(nsamp[0])} ech/record (~{nsamp[0]/fs:.3f} s) | duree {dur_s:.1f} s\n")

    # Analyse ROBUSTE par delta record-a-record : une acquisition peut avoir des trous
    # -> une regression cumulative serait faussee ; on travaille sur les intervalles.
    dsec = np.diff(start) / 1e9                       # s entre debuts de records
    persample = dsec / nsamp[:-1]
    med_ps = float(np.median(persample))             # robuste aux sauts
    fs_eff = 1.0 / med_ps
    drift_ppm = (fs_eff - fs) / fs * 1e6
    med_delta = float(np.median(dsec))
    print(f"Cadence (mediane des intervalles, vs temps GPS) : {med_ps*1e6:.3f} us/ech "
          f"-> fs_eff = {fs_eff:.4f} Hz")
    print(f"  => ecart vs {fs:g} Hz nominal : {drift_ppm:+.1f} ppm "
          f"(quartz ADC local ; l'horodatage RTC suit l'UTC record par record)\n")

    # Quantification de l'horodatage : sous-secondes multiples de 1/N ?
    frac = (start / 1e9) % 1.0
    q = None
    for N in (256, 512, 1024, 32768):
        if np.max(np.abs((frac * N) - np.round(frac * N))) < 0.02:
            q = N
            break
    if q:
        print(f"Resolution d'horodatage RTC = 1/{q} s = {1e3/q:.2f} ms "
              f"(sous-secondes = multiples exacts de 1/{q})")
        print(f"  => PLANCHER de precision d'horodatage +-{1e3/q/2:.2f} ms = le bruit TIME-05.\n")

    # Gigue hors-sauts + detection des sauts (trous/resync)
    dev_ms = (dsec - med_delta) * 1e3
    jumps = np.where(np.abs(dev_ms) > 20.0)[0]        # > 20 ms = trou/saut franc
    normal = dev_ms[np.abs(dev_ms) <= 20.0]
    print(f"Delta record-a-record : nominal {nsamp[0]/fs:.4f} s | mediane {med_delta:.4f} s")
    print(f"  gigue hors-sauts : ecart-type {np.std(normal):.2f} ms "
          f"(~1 pas de quantification)")
    print(f"  sauts (>20 ms) : {len(jumps)}"
          + (f" aux records {[int(j)+1 for j in jumps]} "
             f"(exces {[round(float(dev_ms[j]),1) for j in jumps]} ms)" if len(jumps) else ""))
    if not clean:
        print("  (note: dernier(s) record(s) tronque(s) en transit CDC — finding #6)")

    # Lecture
    print("\n--- Lecture ---")
    print(f"* Cadence : fs_eff = {fs_eff:.3f} Hz ({drift_ppm:+.0f} ppm) — quartz ADC local ; "
          "l'horodatage RTC/PPS porte le vrai temps UTC record par record.")
    if q and q <= 1024:
        print(f"* PRECISION LIMITEE PAR LA RTC : {1e3/q:.1f} ms de quantification "
              f"(prescaler STM32 par defaut 1/{q}). Pour TIME-05/ANT, reconfigurer le "
              "prescaler RTC (async~0, sync~32767) -> ~30 us. => backlog firmware.")
    if len(jumps):
        print(f"* {len(jumps)} saut(s) d'horodatage a investiguer (trou d'acquisition "
              "ou correction PPS brutale).")


if __name__ == "__main__":
    main()
