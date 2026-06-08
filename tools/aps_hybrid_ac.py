"""
Smoke-test AC HYBRIDE : contrôleur d'un axe pilote le shaker d'un AUTRE axe.

Cas d'usage : le contrôleur V étant instable chargé (sa config), on caractérise
le shaker V avec l'électronique H (ctrl H + ampli H), qui le pilote stable.
Câblage banc : capteur shaker V → ctrl H ; ampli H → shaker V ; Wavetek → ce
montage. L'ACCÉLÉROMÈTRE NE CHANGE PAS (on lit juste le canal vertical ai1).

Ce script découple : contrôleur (axe série) et accéléromètre (canal NI).
- ctrl  = APSController(axis=ctrl_axis)   ex. 'horizontal' = ctrl H sur COM6
- accel = Accelerometer(ref_channel=accel_ch)  ex. 1 = accéléro vertical (ai1)

Le ctrl H pilote une charge verticale (gravité) → on lui met un OTT généreux et on
laisse l'armature monter vers le centre au STA (vu stable au test croisé).

⚠️ Ampli H aussi à gain max. Air du shaker V ON. Doigt sur STOP. Petites amplitudes.

Usage :
    python tools/aps_hybrid_ac.py                      # ctrl horizontal, accel ai1, 15 Hz
    python tools/aps_hybrid_ac.py horizontal 1 15 0.1  # explicite
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController                          # noqa: E402
from equipment.wavetek.wavetek import Wavetek39A                # noqa: E402
from equipment.accelerometer.accelerometer import Accelerometer  # noqa: E402

VPP_STEPS = [0.005, 0.01, 0.02, 0.05, 0.1]


def main() -> int:
    ctrl_axis = sys.argv[1] if len(sys.argv) > 1 else "horizontal"
    accel_ch = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    freq = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
    accel_cap_g = float(sys.argv[4]) if len(sys.argv) > 4 else 0.1
    ott = int(sys.argv[5]) if len(sys.argv) > 5 else 300

    ctrl = APSController(axis=ctrl_axis)
    ctrl.connect()
    ctrl.set_overtravel_tolerance(ott)          # OTT généreux : ctrl H pilote une charge verticale
    print(f"[ctrl={ctrl_axis}] OTT={ctrl.get_overtravel_tolerance()} -- STA "
          f"(l'armature V monte vers le centre). Air V ON, main prête.")
    ctrl._send_command("STA")                   # STA brut (ne pas resserrer l'OTT)
    t0 = time.time()
    while time.time() - t0 < 8.0:               # laisser monter/se stabiliser
        time.sleep(0.5)
        if not ctrl.get_start_status():
            print(f"  TRIP au démarrage (t+{time.time()-t0:.1f}s). Augmente OTT ou vérifie l'air.")
            ctrl.disconnect()
            return 1
    print(f"[ctrl={ctrl_axis}] tenu (STA? True). On excite.")

    wav = Wavetek39A()
    accel = Accelerometer(ref_channel=accel_ch)
    wav.connect()
    accel.connect()

    output_on = False
    try:
        wav.set_waveform("sine")
        wav.set_offset(0.0)
        wav.set_frequency(freq)
        print(f"\nAC hybride : ctrl={ctrl_axis}, accel ai{accel_ch}, f={freq} Hz, "
              f"plafond={accel_cap_g} g.")
        print(f"{'Vpp':>8} | {'accel (g)':>10} | {'SNR dB':>7} | {'THD %':>6} | STA?")
        print("-" * 52)
        for vpp in VPP_STEPS:
            wav.set_amplitude(vpp)
            if not output_on:
                wav.enable_output()
                output_on = True
            time.sleep(0.4)
            if not ctrl.get_start_status():
                print(f"{vpp:8.3f} |  --- ctrl a TRIPPÉ ---")
                break
            m = accel.measure(freq, ref_channel=accel_ch)
            on = ctrl.get_start_status()
            print(f"{vpp:8.3f} | {m['accel_g']:10.5f} | {m['snr_db']:7.1f} | "
                  f"{m['thd_percent']:6.1f} | {on}")
            if not on:
                print("  --> TRIP pendant la vibration. Arrêt.")
                break
            if m["accel_g"] > accel_cap_g:
                print(f"  --> plafond {accel_cap_g} g atteint. Arrêt (sécurité).")
                break
    finally:
        if output_on:
            wav.disable_output()
        wav.disconnect()
        accel.disconnect()
        print(f"\n[ctrl={ctrl_axis}] STA? final={ctrl.get_start_status()} "
              f"GES={ctrl.get_last_error()}")
        ctrl.stop()
        ctrl.disconnect()

    print("\nLecture : accel (g) qui monte avec Vpp + SNR correct -> le shaker V "
          "bouge et l'accéléro ai1 répond, piloté par l'électronique H.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
