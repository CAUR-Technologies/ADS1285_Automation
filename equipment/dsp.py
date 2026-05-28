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


def ratio_db(measured: float, reference: float) -> float:
    """Écart en dB entre deux grandeurs : 20·log10(measured/reference)."""
    if reference == 0 or measured <= 0:
        return float("-inf") if measured <= 0 else float("inf")
    return float(20.0 * np.log10(measured / reference))


def linearity_error_db(values) -> float:
    """
    Erreur de linéarité (dB) sur un jeu de sensibilités mesurées à différents
    niveaux d'amplitude : 20·log10(max/min). 0 = parfaitement linéaire.
    """
    vals = [v for v in values if v and v > 0]
    if len(vals) < 2:
        return 0.0
    return float(20.0 * np.log10(max(vals) / min(vals)))


# ─────────────────────────────────────────────────────────────────────────
# Réponse en fréquence d'un géophone (capteur de vitesse) — comparaison
# ─────────────────────────────────────────────────────────────────────────

G_ACCEL = 9.80665  # m/s² par g


def velocity_sensitivity(sens_counts_per_g, freqs):
    """
    Convertit une sensibilité en counts/g (par accélération) vers une
    sensibilité en counts/(m/s) (par vitesse).

    Un géophone est un capteur de VITESSE ; le banc impose une ACCÉLÉRATION.
    Pour un sinus, v = a/(2πf), donc :

        S_v [counts/(m/s)] = S_g [counts/g] · 2πf / g

    Cette conversion retire le facteur 1/f artificiel et révèle la vraie
    réponse du géophone (plate au-dessus de f0, roll-off en f² en dessous).
    Indispensable pour comparer correctement des géophones entre eux.
    """
    s = np.asarray(sens_counts_per_g, dtype=np.float64)
    f = np.asarray(freqs, dtype=np.float64)
    return s * 2.0 * np.pi * f / G_ACCEL


def geophone_velocity_response(freqs, G0: float, f0: float, zeta: float):
    """
    Magnitude de la réponse vitesse d'un géophone (modèle 2ᵉ ordre) :

        |S_v(f)| = G0 · r² / √[ (1-r²)² + (2ζr)² ]   avec r = f/f0

    G0   : sensibilité de bande plate (asymptote haute fréquence)
    f0   : fréquence propre (corner)
    zeta : amortissement (≈ 0,6–0,7 du critique pour un géophone usuel)
    """
    f = np.asarray(freqs, dtype=np.float64)
    r = f / f0
    return G0 * r ** 2 / np.sqrt((1.0 - r ** 2) ** 2 + (2.0 * zeta * r) ** 2)


def fit_geophone_response(freqs, sens_velocity):
    """
    Ajuste le modèle géophone 2ᵉ ordre sur une réponse vitesse mesurée et
    retourne (G0, f0, zeta) + l'erreur résiduelle.

    L'ajustement se fait en échelle log (dB) pour pondérer également toutes
    les décades. Requiert ≥ 4 points valides et scipy ; retourne None sinon.

    Returns dict {G0, f0, zeta, rms_error_db, n} ou None.
    """
    f = np.asarray(freqs, dtype=np.float64)
    s = np.asarray(sens_velocity, dtype=np.float64)
    mask = (f > 0) & (s > 0) & np.isfinite(f) & np.isfinite(s)
    f, s = f[mask], s[mask]
    if len(f) < 4:
        return None
    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return None

    order = np.argsort(f)
    f, s = f[order], s[order]
    # Estimations initiales : G0 ≈ plateau (tiers haute fréquence),
    # f0 ≈ point à -3 dB, zeta ≈ 0,6.
    g0_init = float(np.median(s[-max(1, len(s) // 3):]))
    target = g0_init / np.sqrt(2.0)
    f0_init = float(f[int(np.argmin(np.abs(s - target)))])
    if not np.isfinite(f0_init) or f0_init <= 0:
        f0_init = float(np.sqrt(f[0] * f[-1]))

    def _log_model(ff, g0, f0, zeta):
        return np.log10(geophone_velocity_response(ff, g0, f0, zeta))

    bounds = ([1e-12, f.min() * 0.1, 0.05], [np.inf, f.max() * 5.0, 2.0])
    try:
        popt, _ = curve_fit(_log_model, f, np.log10(s),
                            p0=[g0_init, f0_init, 0.6],
                            bounds=bounds, maxfev=20000)
    except Exception:
        return None
    g0, f0, zeta = float(popt[0]), float(popt[1]), float(popt[2])
    model = geophone_velocity_response(f, g0, f0, zeta)
    resid_db = 20.0 * np.log10(model / s)
    return {
        "G0": g0,
        "f0": f0,
        "zeta": zeta,
        "rms_error_db": float(np.sqrt(np.mean(resid_db ** 2))),
        "n": int(len(f)),
    }


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
