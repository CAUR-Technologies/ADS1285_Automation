#!/usr/bin/env python
"""
TIME-05 — précision/offset d'horodatage de l'unité vs la référence GPS (ProPak).

PRINCIPE
--------
Pendant une excitation sinusoïdale, l'accéléro de référence (daté par le 1PPS
ProPak sur PFI0) ET le géophone de l'unité (daté par son LC86G, via les `.dat`)
voient LE MÊME mouvement. En projetant chaque signal sur `exp(-j2πf·t_gps)` avec
son PROPRE horodatage GPS, la différence de phase par fréquence vaut :

    Δφ(f) = φ_capteur(f)  +  360·f·Δt      [degrés]

où `φ_capteur` = phase (géophone − accéléro), et `Δt` = décalage de l'horloge de
l'unité par rapport à la référence. **Au-dessus de la résonance** (f ≳ 5·f0), la
phase du géophone (réponse vitesse) est ~plate → `Δφ(f) ≈ cste + 360·f·Δt`. La
PENTE de Δφ vs f donne donc `Δt` :  **Δt = pente[deg/Hz] / 360**.

Cette mesure exige la corrélation temps-GPS (`session.correlate`, chemin
`run_excitation` qui capture `ref_signal` + `ref_sods`) — PAS la segmentation
(qui ignore la référence). C'est l'usage COMPLÉMENTAIRE du 1PPS déjà câblé.

ENTRÉE
------
`phase_by_freq` : {freq_hz: Δφ_deg} de la voie sur-axe (sortie `correlate` →
`results[cid][f]["phase_deg"]`).

SORTIE : offset (µs), jitter résiduel (µs), n points, fréquences utilisées.
"""
import sys

import numpy as np


def clock_offset_from_phases(phase_by_freq, f_min_hz=20.0):
    """Estime Δt (offset horloge unité vs référence) par la pente de la rampe de
    phase en HF (où la phase capteur est plate). Retourne dict ou None.

    phase_by_freq : {freq_hz: phase_deg}. f_min_hz : plancher HF (phase géophone
    considérée plate au-delà — régler ≳ 5·f0)."""
    items = sorted((float(f), float(p)) for f, p in phase_by_freq.items()
                   if float(f) >= f_min_hz and np.isfinite(p))
    if len(items) < 2:
        return None
    f = np.array([i[0] for i in items])
    p = np.array([i[1] for i in items])
    # Déroule la phase dans l'ordre des fréquences croissantes (rampe monotone).
    p_unwrapped = np.degrees(np.unwrap(np.radians(p)))
    slope, intercept = np.polyfit(f, p_unwrapped, 1)   # deg/Hz, deg
    offset_s = slope / 360.0
    resid_deg = p_unwrapped - (slope * f + intercept)
    # jitter temporel ~ résidu de phase / (360·f) ; on prend la fréquence médiane.
    jitter_s = (np.std(resid_deg) / 360.0 / np.median(f)) if len(f) else float("nan")
    return {
        "offset_us": offset_s * 1e6,
        "jitter_us": jitter_s * 1e6,
        "n": len(f),
        "freqs_hz": list(f),
        "resid_rms_deg": float(np.std(resid_deg)),
    }


def _self_test():
    """Injecte un Δt connu dans des phases synthétiques et vérifie la récupération."""
    rng_off_us = 250.0                      # décalage injecté (µs)
    dt = rng_off_us * 1e-6
    freqs = [20, 30, 50, 70, 100]
    sensor_phase = -12.0                    # phase capteur plate en HF (deg)
    phases = {}
    for f in freqs:
        # bruit de mesure déterministe (pas de RNG) : petite ondulation
        noise = 0.4 * np.sin(f)             # ~±0,4 deg
        phases[f] = sensor_phase + 360.0 * f * dt + noise
    r = clock_offset_from_phases(phases, f_min_hz=20.0)
    print(f"  injecté  : offset = {rng_off_us:.1f} us")
    print(f"  retrouvé : offset = {r['offset_us']:.1f} us  "
          f"(jitter {r['jitter_us']:.2f} us, résidu {r['resid_rms_deg']:.2f} deg, n={r['n']})")
    ok = abs(r["offset_us"] - rng_off_us) < 5.0
    print("  " + ("OK" if ok else "ECHEC") + " (tolérance 5 us)")
    return ok


if __name__ == "__main__":
    print("TIME-05 auto-test (offset horloge par pente de phase HF) :")
    sys.exit(0 if _self_test() else 1)
