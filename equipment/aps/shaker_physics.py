"""
Physique du shaker — fonctions pures pour la calibration de geophones.

Aucune dependance materielle : tout est calculable et testable hors ligne.

Relations fondamentales (mouvement sinusoidal, acceleration constante) :
    x(t) = A . sin(2.pi.f.t)            -> deplacement crete A
    a(t) = -A.(2.pi.f)^2 . sin(...)     -> acceleration crete a = A.(2.pi.f)^2

D'ou :
    A = a / (2.pi.f)^2

Le deplacement crete est inversement proportionnel au carre de la frequence :
la basse frequence est le cas critique (course mecanique S_max du shaker).

Contraintes :
  * Enveloppe stroke   : A(f) <= S_max  ->  a_max(f) = S_max.(2.pi.f)^2
  * Centrage           : |ZER| + A(f) <= S_max
  * Plafond securite   : a <= accel_cap_g (limite haute frequence)
  * Stiffness          : bande passante du controleur << f_test (>= 1 decade)
"""

import math

# Acceleration de la pesanteur standard (m/s^2)
G = 9.80665


def omega(freq_hz: float) -> float:
    """Pulsation 2.pi.f (rad/s)."""
    return 2.0 * math.pi * freq_hz


def peak_displacement_mm(accel_g: float, freq_hz: float) -> float:
    """
    Deplacement crete (mm) pour une acceleration crete donnee a une frequence.

        A = a / (2.pi.f)^2

    Parameters
    ----------
    accel_g : acceleration crete en g
    freq_hz : frequence en Hz (> 0)
    """
    if freq_hz <= 0:
        raise ValueError("freq_hz doit etre > 0")
    a_ms2 = accel_g * G
    a_m = a_ms2 / (omega(freq_hz) ** 2)
    return a_m * 1000.0


def max_accel_g(freq_hz: float, stroke_mm: float) -> float:
    """
    Acceleration crete maximale (g) avant d'atteindre la course mecanique.

        a_max = S_max . (2.pi.f)^2

    C'est l'enveloppe physique du shaker. A 0,1 Hz pour S_max=38 mm, elle
    vaut ~0,0015 g ; a 2,6 Hz elle atteint deja ~1 g.
    """
    if freq_hz <= 0:
        raise ValueError("freq_hz doit etre > 0")
    stroke_m = stroke_mm / 1000.0
    a_ms2 = stroke_m * (omega(freq_hz) ** 2)
    return a_ms2 / G


def target_accel_g(freq_hz: float,
                   stroke_mm: float,
                   fraction: float = 0.6,
                   accel_cap_g: float = 1.0,
                   accel_floor_g: float | None = None) -> float:
    """
    Acceleration cible (g) pour un point de sweep : fraction constante de
    l'enveloppe stroke, plafonnee a accel_cap_g.

        target = min(fraction . a_max(f), accel_cap_g)

    Mathematiquement, viser une fraction constante de l'enveloppe revient a
    un deplacement constant = fraction . S_max (tant qu'on n'est pas plafonne).

    Parameters
    ----------
    fraction      : fraction de l'enveloppe (0..1), marge de securite overtravel
    accel_cap_g   : plafond absolu (g) impose en haute frequence
    accel_floor_g : si fourni, plancher en dessous duquel on signale que le
                    point est trop faible (ne modifie pas la valeur retournee)
    """
    env = max_accel_g(freq_hz, stroke_mm)
    target = min(fraction * env, accel_cap_g)
    return target


def is_safe(freq_hz: float,
            accel_g: float,
            stroke_mm: float,
            zer_offset_mm: float = 0.0) -> bool:
    """
    Vrai si le mouvement reste dans la course mecanique, offset ZER compris.

        |ZER| + A(f) <= S_max
    """
    A = peak_displacement_mm(accel_g, freq_hz)
    return (abs(zer_offset_mm) + A) <= stroke_mm


def safety_margin_mm(freq_hz: float,
                     accel_g: float,
                     stroke_mm: float,
                     zer_offset_mm: float = 0.0) -> float:
    """
    Marge restante (mm) avant la butee. Negative = overtravel.

        marge = S_max - (|ZER| + A(f))
    """
    A = peak_displacement_mm(accel_g, freq_hz)
    return stroke_mm - (abs(zer_offset_mm) + A)


def stiffness_for_freq(freq_hz: float) -> int:
    """
    Stiffness (STF, 0..31) recommandee selon la frequence de test.

    Regle du manuel APS 0109 : la bande passante du controleur de position
    doit rester >= 1 decade sous la frequence de test pour ne pas "corriger"
    la vibration. On choisit donc une stiffness d'autant plus faible que la
    frequence est basse.

    Bandes (milieu de la plage recommandee dans equipment/CLAUDE.md) :
        f < 1 Hz       -> STF 3   (tres faible)
        1 <= f < 10    -> STF 10
        10 <= f < 50   -> STF 20
        f >= 50 Hz     -> STF 28
    """
    if freq_hz < 1.0:
        return 3
    elif freq_hz < 10.0:
        return 10
    elif freq_hz < 50.0:
        return 20
    else:
        return 28


def accel_to_volts(accel_g: float, sensitivity_v_per_g: float) -> float:
    """Convertit une acceleration crete (g) en tension crete attendue (V)."""
    return accel_g * sensitivity_v_per_g


def volts_to_accel_g(volts: float, sensitivity_v_per_g: float) -> float:
    """Convertit une tension (V) en acceleration (g) via la sensibilite."""
    if sensitivity_v_per_g == 0:
        raise ValueError("sensitivity_v_per_g ne peut pas etre nulle")
    return volts / sensitivity_v_per_g


def lowest_freq_for_accel(accel_g: float, stroke_mm: float) -> float:
    """
    Frequence minimale realisable pour atteindre une acceleration donnee
    sans depasser la course.

        a = S_max.(2.pi.f)^2  ->  f = (1/2pi) . sqrt(a / S_max)
    """
    stroke_m = stroke_mm / 1000.0
    a_ms2 = accel_g * G
    return math.sqrt(a_ms2 / stroke_m) / (2.0 * math.pi)
