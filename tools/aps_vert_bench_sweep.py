"""
Balayage de transfert banc H_banc(f) sur un axe (vertical par défaut), PRUDENT.

Utilise le TestBench réel (enveloppe mécanique, stiffness par bande, servo
d'amplitude, H_banc = a_table/V_wavetek, SNR/THD, abort overtravel) MAIS avec un
servo BRIDÉ : l'ampli vertical est à gain max (~1,4 g/Vpp), donc le pas de servo
par défaut (3 Vpp) ferait plusieurs g. On plafonne donc Vpp et on adoucit le pas.

Le démarrage vertical est hands-free (APSController.start() = OTT-transitoire).

⚠️ SUPERVISÉ : doigt sur STOP (0109), œil sur l'armature. Ctrl+C coupe la sortie
Wavetek (finally). Pas de géophone monté (mesure H_banc).

Usage :
    python tools/aps_vert_bench_sweep.py                 # vertical, freqs par défaut
    python tools/aps_vert_bench_sweep.py vertical 8,12,18,25,35
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equipment.wavetek.wavetek import Wavetek39A                # noqa: E402
from equipment.aps import APSController                          # noqa: E402
from equipment.accelerometer.accelerometer import Accelerometer  # noqa: E402
from equipment.testbench import TestBench                        # noqa: E402
from config.settings import (                                    # noqa: E402
    NI_REF_CHANNEL_VERTICAL,
    NI_REF_CHANNEL_HORIZONTAL,
    SHAKER_STIFFNESS_SCHEDULE,
)

# Servo pour l'axe V CHARGÉ : g/V plus faible (masse) -> il faut plus de Vpp.
# Plafond 1 V (à 15 Hz on a vu 0,975 g à 1 V ; en zone propre ~0,5 g/V).
SAFE_SERVO = dict(
    servo_start_vpp=0.05,
    vpp_max=1.0,            # plafond DUR ; le cap accel (config 0.2 g) borne la force
    servo_tolerance=0.12,
)
DEFAULT_FREQS = [20, 40, 60]   # zone propre, au-dessus de la resonance chargee ~10 Hz


def main() -> int:
    axis = sys.argv[1] if len(sys.argv) > 1 else "vertical"
    if len(sys.argv) > 2:
        freqs = [float(x) for x in sys.argv[2].split(",")]
    else:
        freqs = DEFAULT_FREQS
    ref_ch = NI_REF_CHANNEL_VERTICAL if axis == "vertical" else NI_REF_CHANNEL_HORIZONTAL

    wav = Wavetek39A()
    aps = APSController(axis=axis)
    accel = Accelerometer(ref_channel=ref_ch)
    wav.connect()
    aps.connect()
    accel.connect()

    tb = TestBench(
        wav, aps, accel,
        ref_channel=ref_ch,
        stiffness_schedule=SHAKER_STIFFNESS_SCHEDULE.get(axis),
        **SAFE_SERVO,
    )
    # Pas de montée Vpp max par itération (anti-claquage) — modéré pour le chargé.
    tb._servo_max_step = 0.15

    # Logger console-safe : la console Windows (cp1252) plante sur certains
    # caractères des logs du TestBench (ex. la flèche U+2192). On replace les
    # caractères non encodables au lieu de crasher (le GUI n'a pas ce souci).
    def _safe_log(m):
        try:
            print(m)
        except UnicodeEncodeError:
            print(m.encode("ascii", "replace").decode("ascii"))
    tb.set_logger(_safe_log)

    results = []
    try:
        print(f"\n=== Balayage H_banc {axis} (servo bridé Vpp<={SAFE_SERVO['vpp_max']}) ===")
        print("Centrage ZER…")
        tb.center_zero()
        print(f"Fréquences : {freqs} Hz\n")
        print(f"{'f(Hz)':>6} | {'cible g':>8} | {'Vpp':>6} | {'mes. g':>8} | "
              f"{'H_banc g/V':>11} | {'SNR':>6} | {'THD%':>6} | note")
        print("-" * 88)

        def on_point(r):
            if r.get("skipped"):
                print(f"{r['freq_hz']:6.1f} |   --- IGNORÉ : {r.get('note','')}")
                return
            print(f"{r['freq_hz']:6.1f} | {r['target_g']:8.4f} | {r['vpp']:6.3f} | "
                  f"{r.get('measured_g',0):8.4f} | {r.get('h_bench_g_per_v',0):11.4g} | "
                  f"{r.get('snr_db',0):6.1f} | {r.get('thd_percent',0):6.1f} | {r.get('note','')}")

        results = tb.measure_bench_transfer(freqs, on_point=on_point)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] arrêt demandé.")
    finally:
        try:
            tb._safe_shutdown()
        except Exception:
            pass
        try:
            aps.stop()
        except Exception:
            pass
        wav.disconnect()
        accel.disconnect()
        aps.disconnect()

    ok = [r for r in results if not r.get("skipped")]
    summary = ", ".join(
        "{:.0f}Hz:{:.3g}".format(r["freq_hz"], r.get("h_bench_g_per_v", 0))
        for r in ok
    )
    print(f"\n{len(ok)}/{len(results)} points mesurés. H_banc(f) = {{ {summary} }}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
