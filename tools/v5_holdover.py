"""V5 — discipline PPS : test holdover + resynchronisation.

Sequence operateur : enregistrer avec fix -> DEBRANCHER l'antenne (~holdover) ->
REBRANCHER (le PPS recale la RTC) -> arreter. On mesure, depuis les horodatages .dat :

  * **Segment verrouille (PPS)** : la RTC = UTC ; residu ~plat (au plancher 1/256 s).
  * **Holdover** (antenne debranchee) : la RTC free-run sur le LSE -> le residu DERIVE
    (pente = ecart LSE vs temps verrouille, en ppm).
  * **Resynchronisation** (antenne rebranchee) : le PPS recale la RTC -> **saut** du
    residu (sa taille = l'erreur accumulee en holdover). C'est la PREUVE que le PPS corrige.

Methode : on ancre une droite RTC = a + b*(echantillons cumules) sur les premiers records
(segment verrouille), puis on trace le residu de tous les records. L'horloge ADC (quartz
stable) sert de base de temps ; le residu isole le comportement de la RTC.

Usage :
    python tools/v5_holdover.py                 # dernier .dat
    python tools/v5_holdover.py /survey-data/XX/....dat
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from config.settings import GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID
from tools.pps_stability import _newest_file, _get_most_complete  # noqa: E402


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
        print("GET (transfert robuste) :")
        recs, clean = _get_most_complete(g, target)
    finally:
        try:
            g.close()
        except Exception:  # noqa: BLE001
            pass
    if not recs or len(recs) < 10:
        raise SystemExit(f"Pas assez de records ({len(recs) if recs else 0}).")

    start = np.array([r[0] for r in recs], dtype=np.float64)     # ns
    nsamp = np.array([r[1] for r in recs], dtype=np.float64)
    fs = recs[0][2]
    ncum = np.concatenate([[0], np.cumsum(nsamp)[:-1]])
    t_rel = (start - start[0]) / 1e9                             # s depuis le debut
    print(f"  -> {len(recs)} records | fs {fs:g} Hz | duree {t_rel[-1]:.0f} s"
          + ("" if clean else " (fin tronquee CDC)") + "\n")

    # Ancrage sur le segment verrouille de DEBUT (premiers ~20 records ou 60 s)
    nfit = int(np.sum(t_rel <= 60))
    nfit = max(8, min(nfit, len(recs) - 1))
    A = np.vstack([ncum[:nfit], np.ones(nfit)]).T
    (b, a), *_ = np.linalg.lstsq(A, start[:nfit], rcond=None)
    resid_ms = (start - (a + b * ncum)) / 1e6                    # residu vs droite verrouillee
    fs_lock = 1e9 / b
    print(f"Segment verrouille (0-{t_rel[nfit-1]:.0f} s) : fs = {fs_lock:.4f} Hz, "
          f"residu plat +-{np.std(resid_ms[:nfit]):.1f} ms (plancher 1/256 s)\n")

    # Timeline compacte du residu
    print(f"{'t(s)':>6} {'residu(ms)':>11}   (verrouille ~plat | holdover derive | resync saute)")
    step = max(1, len(recs) // 30)
    for i in range(0, len(recs), step):
        bar = int(np.clip(resid_ms[i] / 2 + 20, 0, 40))
        print(f"{t_rel[i]:>6.0f} {resid_ms[i]:>11.1f}   {'.'*bar}|")

    # Detection du saut de resync = plus grande chute de residu entre records consecutifs
    dres = np.diff(resid_ms)
    k = int(np.argmin(dres))
    step_ms = dres[k]
    print(f"\nSaut de residu le plus fort : {step_ms:+.1f} ms a t={t_rel[k+1]:.0f} s")
    drift_end = float(np.max(np.abs(resid_ms)))
    print(f"Ecart max en holdover (avant recalage) : {drift_end:.1f} ms")

    print("\n--- Lecture ---")
    if step_ms < -8:
        print(f"* RESYNC PPS OBSERVE : la RTC est recalee de {step_ms:.0f} ms a la reprise "
              "du fix -> la discipline PPS corrige bien la derive holdover. V5 (recalage) OK.")
    else:
        print("* Pas de saut franc detecte : soit holdover trop court/LSE tres stable "
              "(derive < plancher 3,9 ms), soit l'antenne n'a pas ete debranchee assez "
              "longtemps. Rallonger le holdover (5+ min) pour un signal net.")
    print(f"* Plancher de precision d'horodatage : 3,9 ms (RTC 1/256 s, backlog FW #8).")


if __name__ == "__main__":
    main()
