"""
Smoke-test AC prudent sur un axe du banc (vertical par defaut).

But : confirmer que le shaker BOUGE et que l'accelerometre de reference REPOND,
sans servo et sans pousser fort. Excitation sinus a frequence fixe, amplitude
Wavetek montee par PETITS PALIERS ; a chaque pas on mesure l'acceleration (g)
et on verifie que le controleur 0109 reste demarre (pas de trip overtravel
pendant la vibration). Arret automatique si :
  - le 0109 trippe (STA? False),
  - l'acceleration depasse le plafond de securite (defaut 0.1 g),
  - erreur d'acquisition.

PRE-REQUIS (axe vertical) : l'operateur doit DEJA avoir etabli le maintien :
armature centree a la main + START au panneau (OTT=50 persiste -> tient a STF=4).
Le script REFUSE de demarrer si STA? n'est pas True.

⚠️ L'ampli APS 125 vertical est a gain MAX : un petit Vpp peut deja bouger fort.
On commence a 5 mV. Garde un doigt sur STOP (panneau) et l'oeil sur l'armature.

Usage :
    python tools/aps_ac_smoketest.py                 # vertical, 15 Hz, cap 0.1 g
    python tools/aps_ac_smoketest.py vertical 10     # 10 Hz
    python tools/aps_ac_smoketest.py vertical 15 0.05  # plafond 0.05 g
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.aps import APSController                      # noqa: E402
from equipment.wavetek.wavetek import Wavetek39A            # noqa: E402
from equipment.accelerometer.accelerometer import Accelerometer  # noqa: E402
from config.settings import (                                # noqa: E402
    NI_REF_CHANNEL_VERTICAL,
    NI_REF_CHANNEL_HORIZONTAL,
)

VPP_STEPS = [0.005, 0.01, 0.02, 0.05, 0.1]   # paliers d'amplitude (Vpp), croissants


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    freq = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    accel_cap_g = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
    ref_ch = NI_REF_CHANNEL_VERTICAL if axis == "vertical" else NI_REF_CHANNEL_HORIZONTAL

    ctrl = APSController(axis=axis)
    ctrl.connect()
    if not ctrl.get_start_status():
        print(f"\n[ABANDON] Le 0109 [{axis}] n'est PAS demarre (STA? False).")
        print("  Etablis d'abord le maintien : centre l'armature + START au panneau,")
        print("  verifie qu'elle tient lachee, PUIS relance ce script.")
        ctrl.disconnect()
        return 1
    print(f"[{axis}] 0109 demarre (STA? True), OTT={ctrl.get_overtravel_tolerance()}. OK.")

    wav = Wavetek39A()
    accel = Accelerometer(ref_channel=ref_ch)
    wav.connect()
    accel.connect()

    output_on = False
    try:
        wav.set_waveform("sine")
        wav.set_offset(0.0)
        wav.set_frequency(freq)
        print(f"\nSmoke-test AC : axe={axis}, f={freq} Hz, plafond={accel_cap_g} g, "
              f"accelero canal ai{ref_ch}.")
        print(f"{'Vpp':>8} | {'accel (g)':>10} | {'SNR dB':>7} | {'THD %':>6} | STA?")
        print("-" * 52)

        for vpp in VPP_STEPS:
            wav.set_amplitude(vpp)
            if not output_on:
                wav.enable_output()
                output_on = True
            time.sleep(0.4)                       # stabilisation
            if not ctrl.get_start_status():
                print(f"{vpp:8.3f} |  --- 0109 a TRIPPE avant mesure ---")
                break
            m = accel.measure(freq, ref_channel=ref_ch)
            still_on = ctrl.get_start_status()
            print(f"{vpp:8.3f} | {m['accel_g']:10.5f} | {m['snr_db']:7.1f} | "
                  f"{m['thd_percent']:6.1f} | {still_on}")
            if not still_on:
                print("  --> 0109 a TRIPPE pendant la vibration (AC hors fenetre ?). Arret.")
                break
            if m["accel_g"] > accel_cap_g:
                print(f"  --> plafond {accel_cap_g} g atteint. Arret (par securite).")
                break
    finally:
        if output_on:
            wav.disable_output()
        wav.disconnect()
        accel.disconnect()
        print(f"\n[{axis}] STA? final = {ctrl.get_start_status()}  GES={ctrl.get_last_error()}")
        ctrl.disconnect()

    print("\nLecture : si accel (g) MONTE avec Vpp et SNR correct -> le shaker bouge")
    print("et l'accelero repond. Si accel reste ~0 -> rien n'arrive au shaker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
