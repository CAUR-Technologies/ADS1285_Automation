#!/usr/bin/env python
"""
CORRÉLATION TEMPORELLE (TIME-05) — but PREMIER du banc shaker+GNSS.

Mesure l'**offset d'horodatage de l'unité** (LC86G) vs la **référence GPS**
(ProPak, 1PPS sur PFI0). C'est LA validation clé pour l'ANT : les enregistrements
de plusieurs unités ne sont **cross-corrélables** que si leurs horloges s'accordent.

Principe : le shaker fournit un **signal commun** vu simultanément par l'accéléro de
référence (daté 1PPS ProPak, temps GPS) et le géophone de l'unité (daté LC86G dans
le `.dat`). En projetant chaque signal sur son PROPRE temps GPS, la différence de
phase par fréquence vaut `Δφ(f) = φ_capteur(f) + 360·f·Δt`. Au-dessus de la
résonance la phase capteur est ~plate → la PENTE de Δφ vs f donne `Δt` (offset
horloge). Voir `tools/time_offset.py`.

Standalone (UNE seule tâche NI accéléro + le compteur 1PPS → pas de conflit avec un
servo bench concurrent). HAUTES fréquences seulement (100→20 Hz) → déplacement µm,
pas de risque de butée. Sécurité anti-emballement : `check_reference_alive` avant
toute excitation.

⚠️ PRÉREQUIS : ZER centré (via le GUI), shaker+ampli+accéléro réf.+GNSS ProPak (fix)
câblés, unité montée sur l'axe choisi. 1re validation matérielle du chemin
`run_excitation` — à roder.

Usage :
    python tools/time_correlation.py --axis vertical
    python tools/time_correlation.py --axis horizontal --dwell 12
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from equipment.wavetek import Wavetek39A
from equipment.aps import APSController
from equipment.accelerometer.accelerometer import Accelerometer
from equipment.testbench import TestBench
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from equipment.geophone3axis.session import Characterize3AxisSession
from equipment.gnss.gnss import Gnss
from equipment.gnss.pps import Pps1ppsMonitor
from tools.time_offset import clock_offset_from_phases
from config.settings import (
    WAVETEK_PORT, WAVETEK_BAUD, APS_CONTROLLER_HORIZONTAL_PORT,
    APS_CONTROLLER_VERTICAL_PORT, NI_DEVICE_NAME, NI_AI_CHANNELS, NI_SAMPLE_RATE,
    NI_SAMPLES_PER_CHANNEL, NI_REF_CHANNEL_HORIZONTAL, NI_REF_CHANNEL_VERTICAL,
    SHAKER_STIFFNESS_SCHEDULE, GNSS_PORT, GNSS_BAUD,
    GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID, GEOPHONE3AXIS_DATA_DIR)

try:
    from config.settings import SERVO_VPP_MAX_3AXIS
except ImportError:
    from gui_3axis import SERVO_VPP_MAX_3AXIS

OUT_DIR = "data/time_correlation"
FREQS = [100.0, 70.0, 50.0, 30.0, 20.0]   # bande HF : phase géophone ~plate → pente = Δt


def run(axis="horizontal", dwell=10.0, gain=1):
    os.makedirs(OUT_DIR, exist_ok=True)
    ref_ch = NI_REF_CHANNEL_HORIZONTAL if axis == "horizontal" else NI_REF_CHANNEL_VERTICAL
    aps_port = APS_CONTROLLER_HORIZONTAL_PORT if axis == "horizontal" else APS_CONTROLLER_VERTICAL_PORT

    print(f"=== CORRÉLATION TEMPORELLE (TIME-05) — axe {axis}, ai{ref_ch} ===")
    wav = Wavetek39A(port=WAVETEK_PORT, baud=WAVETEK_BAUD); wav.connect()
    aps = APSController(axis=axis, port=aps_port); aps.connect()
    accel = Accelerometer(device=NI_DEVICE_NAME, channels=NI_AI_CHANNELS,
                          sample_rate=NI_SAMPLE_RATE, samples_per_channel=NI_SAMPLES_PER_CHANNEL,
                          ref_channel=ref_ch)
    accel.connect()
    bench = TestBench(wav, aps, accel, None, vpp_max=SERVO_VPP_MAX_3AXIS,
                      stiffness_schedule=SHAKER_STIFFNESS_SCHEDULE.get(axis), ref_channel=ref_ch)
    bench.set_logger(print)

    found = discover_units(vid=GEOPHONE3AXIS_VID, pid=GEOPHONE3AXIS_PID)
    if not found:
        print("Aucune unité détectée."); return
    sn, port = found[0]
    unit = Geophone3Axis(port, serial_number=sn); unit.connect()
    gnss = Gnss(port=GNSS_PORT, baud=GNSS_BAUD); gnss.connect()
    pps = Pps1ppsMonitor(device=NI_DEVICE_NAME, pfi_terminal="PFI0", counter="ctr0")

    sess = Characterize3AxisSession(bench, unit, gnss, pps, GEOPHONE3AXIS_DATA_DIR)
    lsb_v = 2.5 / gain / (2 ** 31)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    survey = f"TIMECORR_{ts}"
    result = {"serial": sn, "axis": axis, "timestamp": ts}
    try:
        # Anti-emballement : l'accéléro doit lire un signal plausible AVANT excitation.
        bench.check_reference_alive()
        unit.set_config({"sample_rate_hz": 250, "samples_by_record": 250,
                         "records_per_file": 8, "gain": gain, "survey_id": survey,
                         "max_pitch_deg": 45, "max_roll_deg": 45})
        sess.start_unit(f"/survey-data/{survey}")     # record vérifié
        acq = sess.run_excitation(FREQS, dwell_s=dwell)   # excite + capture réf. 1PPS
        sess.stop_unit()
        sess.retrieve_files(f"/survey-data/{survey}")
        corr = sess.correlate(acq["schedule"], acq["ref_signal"], acq["ref_sods"],
                              sens_v_per_g=acq["sens_v_per_g"], lsb_v=lsb_v)
    finally:
        try: bench._safe_shutdown()
        except Exception: pass
        try: wav.disable_output()
        except Exception: pass
        for c in (wav, aps, accel, unit, gnss):
            try: c.close() if hasattr(c, "close") else c.disconnect()
            except Exception: pass

    # Voie sur-axe = plus de counts ; phase par fréquence → offset horloge.
    if not corr:
        print("Aucune voie corrélée (.dat vide / pas de 1PPS ?)."); return
    on_axis = max(corr, key=lambda c: sum(d.get("counts_peak", 0) for d in corr[c].values()))
    phase_by_f = {f: d["phase_deg"] for f, d in corr[on_axis].items()
                  if np.isfinite(d.get("phase_deg", np.nan))}
    print(f"\nvoie sur-axe {on_axis} — phase Δφ(f) unité↔réf :")
    for f in sorted(phase_by_f, reverse=True):
        print(f"  {f:>6.0f} Hz : {phase_by_f[f]:+7.2f} deg")
    off = clock_offset_from_phases(phase_by_f, f_min_hz=20.0)
    result["on_axis_channel"] = on_axis
    result["phase_by_freq"] = phase_by_f
    result["offset"] = off
    if off:
        print(f"\n>>> OFFSET HORLOGE unité↔réf = {off['offset_us']:+.1f} µs "
              f"(jitter {off['jitter_us']:.1f} µs, résidu {off['resid_rms_deg']:.2f} deg, n={off['n']}) <<<")
    else:
        print("\n>>> offset non calculable (< 2 points HF valides) <<<")
    with open(os.path.join(OUT_DIR, f"{sn}_{ts}.json"), "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2, ensure_ascii=False)
    print(f"→ {OUT_DIR}/{sn}_{ts}.json")


if __name__ == "__main__":
    a = sys.argv
    axis = a[a.index("--axis") + 1] if "--axis" in a else "horizontal"
    dwell = float(a[a.index("--dwell") + 1]) if "--dwell" in a else 10.0
    run(axis=axis, dwell=dwell)
