"""
Spécifications des géophones candidats à la calibration et calcul de la
vitesse crête maximale tolérée (anti-saturation du géophone).

Un géophone sort une tension proportionnelle à la VITESSE :

    V_géo(f) = G · v · |H(f)|

où G est la sensibilité (V/(m/s), circuit ouvert) et |H(f)| la réponse
normalisée (≈ 1 dans la bande plate au-dessus de f0). Pour un géophone
SOUS-AMORTI (ζ < 1/√2), |H| dépasse 1 près de f0 : le pic vaut

    |H|_max = 1 / (2ζ·√(1-ζ²))

(ex. HG-5VHS, ζ=0,268 → pic ×1,94). La saturation se produit donc au pic,
pas dans la bande plate : la vitesse max sûre en tient compte.

    v_max = safety · V_pleine_échelle / (G · |H|_max)

La sensibilité circuit ouvert est le cas le plus défavorable (sortie max) :
chargé par la résistance de bobine + amortissement + entrée ADC, le géophone
sort moins → marge supplémentaire.
"""

import math

# nom : (sensibilité V/(m/s) circuit ouvert, f0 Hz, amortissement ζ, note)
# Données : datasheets / tableau de collection des géophones.
GEOPHONE_SPECS: dict[str, tuple[float, float, float, str]] = {
    "HG-5VHS":     (100.4, 5.0, 0.268, "HGS — très haute sensibilité"),
    "HG-6 HB":     (28.8,  4.5, 0.56,  "HGS — équivalent SM-6"),
    "HG-6XT UB":   (28.8,  4.5, 0.56,  "HGS — tilt étendu"),
    "HG-2 U":      (50.0,  2.5, 0.5,   "HGS 2,5 Hz — sensibilité estimée (~40-50)"),
    "VAS-200 (V)": (220.0, 4.5, 0.73,  "Sunfull — composante Z (3C)"),
    "VAS-H-200":   (220.0, 4.5, 0.73,  "Sunfull — composantes horizontales (3C)"),
    "ST-2A (V)":   (260.0, 2.0, 0.7,   "Seis Tech — ondes P"),
    "ST-2A (H)":   (260.0, 2.0, 0.7,   "Seis Tech — ondes S"),
}

_CRITICAL = 1.0 / math.sqrt(2.0)   # ζ = 0,7071 : limite du pic de résonance


def resonance_peak(damping: float) -> float:
    """
    Facteur de pic de la réponse vitesse d'un géophone 2ᵉ ordre.

    |H|_max = 1/(2ζ√(1-ζ²)) si ζ < 1/√2, sinon 1 (réponse monotone, sans pic).
    """
    z = damping
    if z <= 0.0 or z >= _CRITICAL:
        return 1.0
    return 1.0 / (2.0 * z * math.sqrt(1.0 - z * z))


def max_safe_velocity_mps(name: str,
                          fs_peak_v: float,
                          safety: float = 0.5,
                          fallback: float = 0.01) -> float:
    """
    Vitesse crête maximale (m/s) du shaker pour que la sortie du géophone
    *name* reste sous *safety* × pleine échelle ADC, pic de résonance compris.

    fs_peak_v : tension crête pleine échelle de l'ADS1285 (V) à la PGA gain
                utilisée (±2,5 V à gain 1).
    safety    : fraction de la pleine échelle visée (défaut 0,5).
    fallback  : valeur retournée si le géophone est inconnu.
    """
    spec = GEOPHONE_SPECS.get(name)
    if spec is None:
        return fallback
    sensitivity, _f0, damping, _note = spec
    if sensitivity <= 0:
        return fallback
    return safety * fs_peak_v / (sensitivity * resonance_peak(damping))
