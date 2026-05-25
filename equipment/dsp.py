"""
Utilitaires de traitement du signal partagés.

Détection cohérente mono-bin (lock-in numérique) : extrait l'amplitude d'une
sinusoïde à une fréquence connue en rejetant le bruit et les autres
composantes. Essentiel pour les signaux à faible rapport signal/bruit
(ex. accéléromètre à 0,0015 g ≈ 1,2 mV en très basse fréquence).
"""

import numpy as np


def coherent_amplitude_peak(signal, freq_hz: float, fs: float) -> float:
    """
    Amplitude crête d'une sinusoïde à freq_hz dans signal, par projection
    cohérente sur exp(-j.2.pi.f.t).

        X = Σ (x[n] - moyenne) . exp(-j 2pi f n / fs)
        amplitude_crête = 2.|X| / N

    Parameters
    ----------
    signal : séquence d'échantillons
    freq_hz : fréquence cible (Hz)
    fs : fréquence d'échantillonnage (Hz)
    """
    x = np.asarray(signal, dtype=np.float64)
    if len(x) == 0:
        return 0.0
    n = np.arange(len(x))
    basis = np.exp(-2j * np.pi * freq_hz * n / fs)
    X = np.dot(x - x.mean(), basis)
    return float(2.0 * np.abs(X) / len(x))
