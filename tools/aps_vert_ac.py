"""
Démarrage tenu + smoke-test AC sur un axe (vertical par défaut), EN UN SEUL run.

Pourquoi : au STA le démarrage est souple (SSS bas), l'armature verticale plonge
sous la gravité avant que le contrôleur ne développe sa force ; cette plongée
dépasse la fenêtre OTT et arme un trip overtravel (le 0109 récupère à zéro puis
coupe). La parade validée : TENIR l'armature centrée pendant le démarrage. Ce
script enchaîne sans jamais arrêter le contrôleur : (1) STA + maintien STF tenu,
(2) confirmation hands-free, (3) AC par paliers, (4) arrêt propre.

⚠️ Ampli vertical à gain MAX : on commence à 5 mV, plafond accel 0.1 g. Doigt sur
STOP, œil sur l'armature.

Déroulé pour l'opérateur (par l'oreille, top = CLIC du relais START) :
  - AVANT de lancer : tiens l'armature CENTRÉE fermement.
  - CLIC (STA) -> garde centré, compte lentement jusqu'à 5.
  - quand tu peux relâcher : le script l'annonce dans le log (mais tu ne le vois
    pas en direct) -> relâche après ton compte de 5 ; s'il a trippé il s'arrête.
  - ensuite l'AC démarre tout seul (petits paliers).

Usage :
    python tools/aps_vert_ac.py                  # vertical, 15 Hz, STF 4, cap 0.1 g
    python tools/aps_vert_ac.py vertical 10 4 0.05
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController                          # noqa: E402
from equipment.wavetek.wavetek import Wavetek39A                # noqa: E402
from equipment.accelerometer.accelerometer import Accelerometer  # noqa: E402
from config.settings import (                                    # noqa: E402
    NI_REF_CHANNEL_VERTICAL,
    NI_REF_CHANNEL_HORIZONTAL,
)

VPP_STEPS = [0.005, 0.01, 0.02, 0.05, 0.1]


def _hold_start(ctrl, axis, stf, capture_s=5.0, confirm_s=3.0) -> bool:
    """STA + maintien STF tenu (opérateur centre), puis confirme le maintien
    hands-free. Retourne True si le contrôleur tient, False s'il a trippé."""
    print(f"[{axis}] OTT={ctrl.get_overtravel_tolerance()}  -- tiens l'armature CENTREE.")
    print(">>> STA (CLIC) -- garde centre, compte jusqu'a 5.")
    ctrl.start()
    t0 = time.time()
    while time.time() - t0 < capture_s:
        time.sleep(0.5)
        try:
            ctrl.set_stiffness(stf)          # STF ne prend qu'en marche ; re-assert
        except Exception:                    # noqa: BLE001
            pass
        if not ctrl.get_start_status():
            print(f"  TRIP pendant le maintien (t+{time.time()-t0:.1f}s) -- "
                  f"tiens plus fermement CENTRE et relance.")
            return False
    print("  --> RELACHE doucement l'armature. Verification du maintien...")
    t1 = time.time()
    while time.time() - t1 < confirm_s:
        time.sleep(0.5)
        if not ctrl.get_start_status():
            print(f"  TRIP apres relache (t+{time.time()-t1:.1f}s).")
            return False
    print(f"[{axis}] maintien CONFIRME hands-free (STF={ctrl.get_stiffness()}).")
    return True


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    freq = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    stf = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    accel_cap_g = float(sys.argv[4]) if len(sys.argv) > 4 else 0.1
    ref_ch = NI_REF_CHANNEL_VERTICAL if axis == "vertical" else NI_REF_CHANNEL_HORIZONTAL

    ctrl = APSController(axis=axis)
    ctrl.connect()

    if not _hold_start(ctrl, axis, stf):
        ctrl.stop()
        ctrl.disconnect()
        return 1

    wav = Wavetek39A()
    accel = Accelerometer(ref_channel=ref_ch)
    wav.connect()
    accel.connect()

    output_on = False
    try:
        wav.set_waveform("sine")
        wav.set_offset(0.0)
        wav.set_frequency(freq)
        print(f"\nAC : axe={axis}, f={freq} Hz, plafond={accel_cap_g} g, accelero ai{ref_ch}.")
        print(f"{'Vpp':>8} | {'accel (g)':>10} | {'SNR dB':>7} | {'THD %':>6} | STA?")
        print("-" * 52)
        for vpp in VPP_STEPS:
            wav.set_amplitude(vpp)
            if not output_on:
                wav.enable_output()
                output_on = True
            time.sleep(0.4)
            if not ctrl.get_start_status():
                print(f"{vpp:8.3f} |  --- 0109 a TRIPPE ---")
                break
            m = accel.measure(freq, ref_channel=ref_ch)
            on = ctrl.get_start_status()
            print(f"{vpp:8.3f} | {m['accel_g']:10.5f} | {m['snr_db']:7.1f} | "
                  f"{m['thd_percent']:6.1f} | {on}")
            if not on:
                print("  --> TRIP pendant la vibration. Arret.")
                break
            if m["accel_g"] > accel_cap_g:
                print(f"  --> plafond {accel_cap_g} g atteint. Arret (securite).")
                break
    finally:
        if output_on:
            wav.disable_output()
        wav.disconnect()
        accel.disconnect()
        print(f"\n[{axis}] STA? final={ctrl.get_start_status()}  GES={ctrl.get_last_error()}")
        ctrl.stop()
        ctrl.disconnect()

    print("\nLecture : accel (g) qui MONTE avec Vpp + SNR correct -> shaker bouge,")
    print("accelero repond. accel ~0 -> rien n'arrive au shaker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
