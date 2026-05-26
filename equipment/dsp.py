"""
Utilitaires de traitement du signal partagés.

Détection cohérente mono-bin (lock-in numérique) : extrait l'amplitude d'une
sinusoïde à une fréquence connue en rejetant le bruit et les autres
composantes. Essentiel pour les signaux à faible rapport signal/bruit
(ex. accéléromètre à 0,0015 g ≈ 1,2 mV en très basse fréquence).
"""

import numpy as np


def coherent_phasor(signal, freq_hz: float, fs: float) -> complex:
    """
    Phaseur complexe (amplitude crête + phase) d'une sinusoïde à freq_hz par
    projection cohérente sur exp(-j.2.pi.f.t).

        X = Σ (x[n] - moyenne) . exp(-j 2pi f n / fs)
        phaseur = 2.X / N   (module = amplitude crête, argument = phase)
    """
    x = np.asarray(signal, dtype=np.float64)
    if len(x) == 0:
        return 0j
    n = np.arange(len(x))
    basis = np.exp(-2j * np.pi * freq_hz * n / fs)
    X = np.dot(x - x.mean(), basis)
    return complex(2.0 * X / len(x))


def coherent_amplitude_peak(signal, freq_hz: float, fs: float) -> float:
    """
    Amplitude crête d'une sinusoïde à freq_hz (module du phaseur cohérent).

    Rejette le bruit et les autres composantes : robuste à SNR négatif.
    """
    return float(abs(coherent_phasor(signal, freq_hz, fs)))


def rms(signal) -> float:
    """Valeur efficace (RMS) du signal, composante continue retirée."""
    x = np.asarray(signal, dtype=np.float64)
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean((x - x.mean()) ** 2)))


def snr_db(signal, freq_hz: float, fs: float) -> float:
    """
    Rapport signal/bruit (dB) : puissance de la composante cohérente à freq_hz
    vs puissance résiduelle (tout le reste).
    """
    x = np.asarray(signal, dtype=np.float64)
    a = coherent_amplitude_peak(x, freq_hz, fs)
    p_sig = (a / np.sqrt(2.0)) ** 2
    p_tot = float(np.var(x))
    p_noise = max(p_tot - p_sig, 1e-30)
    if p_sig <= 0:
        return float("-inf")
    return float(10.0 * np.log10(p_sig / p_noise))


def thd_percent(signal, freq_hz: float, fs: float, n_harmonics: int = 5) -> float:
    """
    Distorsion harmonique totale (%) : sqrt(Σ A_k²) / A_1 × 100, k=2..n.

    Les harmoniques au-delà de Nyquist sont ignorées.
    """
    x = np.asarray(signal, dtype=np.float64)
    a1 = coherent_amplitude_peak(x, freq_hz, fs)
    if a1 <= 0:
        return 0.0
    acc = 0.0
    for k in range(2, n_harmonics + 1):
        fk = k * freq_hz
        if fk >= fs / 2.0:
            break
        acc += coherent_amplitude_peak(x, fk, fs) ** 2
    return float(np.sqrt(acc) / a1 * 100.0)
