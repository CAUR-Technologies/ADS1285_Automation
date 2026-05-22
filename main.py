"""
Script principal d'automatisation des mesures.

Séquence type :
  1. Connexion à tous les équipements
  2. Configuration initiale
  3. Balayage fréquentiel (ou autre séquence de test)
  4. Acquisition synchronisée ADS1285 + Accéléromètres
  5. Sauvegarde des données
  6. Déconnexion propre
"""

import os
import time
import numpy as np
import matplotlib.pyplot as plt

from config.settings import DATA_OUTPUT_DIR
from equipment.ads1285 import ADS1285
from equipment.aps import APSController
from equipment.wavetek import Wavetek39A
from equipment.accelerometer import Accelerometer


# ---------------------------------------------------------------------------
# Paramètres du test
# ---------------------------------------------------------------------------
FREQUENCIES_HZ = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]  # balayage fréquentiel
AMPLITUDE_VPP = 1.0       # amplitude du générateur en Vpp
STABILIZATION_S = 2.0     # temps d'attente après changement de fréquence (s)
NUM_ADC_SAMPLES = 4096    # nombre d'échantillons ADS1285 par mesure


def run_frequency_sweep() -> dict:
    """
    Effectue un balayage fréquentiel et retourne les résultats.
    Retourne un dict {freq_hz: {"adc": [...], "accel": np.array}}.
    """
    results = {}

    with (
        ADS1285() as adc,
        APSController("vertical")   as aps_ctrl_v,
        APSController("horizontal") as aps_ctrl_h,
        Wavetek39A() as wavetek,
        Accelerometer() as accel,
    ):
        # Configuration initiale
        wavetek.set_waveform("sine")
        wavetek.set_amplitude(AMPLITUDE_VPP)

        for freq in FREQUENCIES_HZ:
            print(f"\n--- Fréquence : {freq} Hz ---")
            wavetek.set_frequency(freq)
            time.sleep(STABILIZATION_S)

            # Acquisition simultanée
            adc_data = adc.acquire(NUM_ADC_SAMPLES)
            accel_data = accel.acquire()

            results[freq] = {
                "adc": adc_data,
                "accel": accel_data,
            }
            print(f"  ADC  : {len(adc_data)} échantillons acquis.")
            print(f"  Accél: {accel_data.shape} acquis.")

        # Arrêt propre
        wavetek.disable_output()

    return results


def save_results(results: dict) -> None:
    """Sauvegarde les résultats en fichiers .npz dans DATA_OUTPUT_DIR."""
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_OUTPUT_DIR, f"sweep_{timestamp}.npz")
    save_dict = {}
    for freq, data in results.items():
        key = f"f{freq:.1f}Hz"
        save_dict[f"{key}_adc"] = np.array(data["adc"])
        save_dict[f"{key}_accel"] = data["accel"]
    np.savez(out_path, **save_dict)
    print(f"\nRésultats sauvegardés : {out_path}")


def plot_results(results: dict) -> None:
    """Affiche un graphique d'amplitude vs fréquence pour chaque canal accéléromètre."""
    freqs = sorted(results.keys())
    amplitudes = [np.max(np.abs(results[f]["accel"])) for f in freqs]

    plt.figure(figsize=(10, 5))
    plt.semilogx(freqs, amplitudes, "o-")
    plt.xlabel("Fréquence (Hz)")
    plt.ylabel("Amplitude accéléromètre (V)")
    plt.title("Réponse fréquentielle — Table de vibration APS")
    plt.grid(True, which="both", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    print("=== Démarrage de la séquence de mesure ===")
    results = run_frequency_sweep()
    save_results(results)
    plot_results(results)
    print("\n=== Mesure terminée ===")
