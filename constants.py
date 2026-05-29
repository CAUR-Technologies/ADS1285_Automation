"""
Constantes physiques et matérielles — source unique de vérité.

Distinction importante avec config.ini :
  * constants.py  -> faits matériels IMMUABLES (specs constructeur, seuils
                     métrologiques, physique). Ne change jamais à l'usage.
  * config.ini    -> paramètres RÉGLABLES par installation (ports COM,
                     fraction d'enveloppe, sensibilité mesurée, modèle de
                     géophone…), édités via le GUI -> config/settings.py.

Les valeurs réglables NE sont PAS dupliquées ici pour éviter deux sources
de vérité. Quand une grandeur est à la fois une spec matérielle et un
réglage (ex. course du shaker), la valeur canonique est ici et config.ini
en porte une copie ajustable par l'opérateur.
"""

# ───────────────────────────────────────────────────────────────────────
# Physique
# ───────────────────────────────────────────────────────────────────────
G = 9.80665                 # accélération de la pesanteur standard (m/s²)

# ───────────────────────────────────────────────────────────────────────
# APS 113 — Shaker (ELEKTRO-SEIS)
# ───────────────────────────────────────────────────────────────────────
APS113_STROKE_MM      = 38.0      # demi-course mécanique max ±38 mm
APS113_FORCE_MAX_N    = 133.0     # force sinusoïdale max (N)
APS113_MASS_MOVING_KG = 0.5       # masse de l'armature seule (kg)
APS113_FREQ_MIN_HZ    = 0.1       # fréquence minimale utile
APS113_FREQ_MAX_HZ    = 200.0     # fréquence maximale utile

# ───────────────────────────────────────────────────────────────────────
# APS 0109 — Contrôleur de position (SPEKTRA), RS232
# ───────────────────────────────────────────────────────────────────────
APS0109_BAUD          = 19200
APS0109_BYTESIZE      = 8
APS0109_PARITY        = "N"
APS0109_STOPBITS      = 1
APS0109_TERMINATOR    = b"\x00"
APS0109_ZER_RANGE     = (-99, 99)     # position zéro
APS0109_STF_RANGE     = (0, 31)       # stiffness
APS0109_OTT_RANGE     = (0, 1023)     # tolérance overtravel
APS0109_PMA_PMI_RANGE = (0, 1023)     # limites position (comptes ADC)

# ───────────────────────────────────────────────────────────────────────
# APS 125 — Amplificateur de puissance (contrôle MANUEL uniquement)
# ───────────────────────────────────────────────────────────────────────
APS125_POWER_MAX_VA   = 500.0
APS125_VOLTAGE_MAX_V  = 45.0
APS125_CURRENT_MAX_A  = 11.0
APS125_LOAD_OHM       = 4.0
APS125_REMOTE_CONTROL = False     # pas d'interface série — knobs manuels

# ───────────────────────────────────────────────────────────────────────
# Accéléromètre de référence
# ───────────────────────────────────────────────────────────────────────
# MEMS Silicon Designs 2240-005 -> boîte Spektra -> NI USB-6221.
# Sensibilité de chaîne réglable dans config.ini (Shaker/accel_sensitivity_v_per_g)
# car elle dépend d'un éventuel gain de la boîte Spektra.
ACCEL_REF_MODEL          = "Silicon Designs 2240-005"
ACCEL_REF_SENS_V_PER_G   = 0.8     # 800 mV/g (valeur capteur nominale)
ACCEL_REF_RANGE_G        = 5.0     # ±5 g

# ───────────────────────────────────────────────────────────────────────
# Seuils métrologiques de calibration
# ───────────────────────────────────────────────────────────────────────
SAFETY_MARGIN          = 0.7      # fraction du stroke utilisable (marge)
SNR_MIN_DB             = 20.0     # SNR minimum acceptable par point
CAL_N_CYCLES           = 20       # cycles acquis par fréquence
CAL_THD_MAX_PERCENT    = 3.0      # distorsion harmonique totale max
CAL_LINEARITY_MAX_DB   = 1.0      # écart de linéarité max
CAL_CROSS_AXIS_MAX_PCT = 5.0      # sensibilité transversale max
CAL_DAILY_TOL_DB       = 0.5      # écart vérif. quotidienne -> recal. complet
CAL_INVALIDATE_DB      = 1.0      # écart -> étalonnage invalide

# Grille de fréquences de calibration (Hz)
CAL_FREQS_HZ = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]

# Fréquences de vérification quotidienne rapide (Hz)
CAL_DAILY_FREQS_HZ = [1, 10, 50]
