# Protocole d'étalonnage du banc et des géophones

Référence métrologique du système. Implémentation : `equipment/testbench.py`,
`equipment/dsp.py`, `equipment/aps/shaker_physics.py`. Seuils : `constants.py`.

## Principe — calibration en deux étapes

```
H_banc(f)   = a_table(f) / V_wavetek(f)              [g/V, amplitude (+ phase)]
H_géo(f)    = V_géo(f) / [V_wavetek(f) · H_banc(f)]  = V_géo(f) / a_table(f)
```

- `a_table(f)` : accélération mesurée par l'accéléromètre de référence (NI).
- `V_wavetek(f)` : amplitude commandée du générateur.
- `V_géo(f)` : sortie du géophone (DUT) numérisée par l'ADS1285.

Mesurer `H_banc` séparément permet : caractérisation indépendante du banc,
vérification quotidienne, détection de dérive, et prédiction de l'amplitude
Wavetek nécessaire (feed-forward) en plus du servo en boucle fermée.

## Ordre des mesures (étalonnage complet)

1. **Plancher de bruit** — shaker arrêté, ampli allumé, ~60 s. Établit le
   bruit de fond ; sert au calcul du SNR par point (seuil `SNR_MIN_DB` = 20 dB).
2. **Fonction de transfert du banc `H_banc(f)`** — grille log 0,1–100 Hz.
   Pour chaque f : enveloppe → cible (`SAFETY_MARGIN` = 0,7 du stroke,
   plafond 1 g) → stiffness adaptée → servo amplitude → mesure `a_table`.
3. **Linéarité** — 3 niveaux × 5 fréquences ; écart max `CAL_LINEARITY_MAX_DB` = 1 dB.
4. **THD** — distorsion harmonique totale, seuil max `CAL_THD_MAX_PERCENT` = 3 %.
5. **Sensibilité transversale** (cross-axis) — seuil max `CAL_CROSS_AXIS_MAX_PCT`
   = 5 %. Deux phases : excitation **le long** de l'axe sensible (`S_main`), puis
   **perpendiculaire** après remontage du géophone (`S_trans`) ; transversale =
   `S_trans / S_main × 100`. L'axe non excité est muté par `STP` du contrôleur
   (coupe l'AC) ; chaque phase lit l'accéléromètre de référence de son axe.

## Contraintes physiques (rappel)

- Enveloppe : `A(f) = a/(2πf)² ≤ S_max` (38 mm). La basse fréquence est critique.
- Stiffness adaptée à la fréquence (bande passante contrôleur ≪ f_test).
- Centrage ZER avant tout signal AC ; `|ZER| + A(f) ≤ S_max`.
- Détection cohérente obligatoire en basse fréquence (signal ≈ 1 mV à 0,0015 g).

## Invalidation — refaire l'étalonnage complet si

- Position des knobs de l'APS 125 modifiée.
- Remplacement de l'accéléromètre de référence.
- Déplacement physique du banc.
- Écart > `CAL_INVALIDATE_DB` = 1 dB lors d'une vérification.

## Vérification quotidienne (rapide)

Mesurer `H_banc` à `CAL_DAILY_FREQS_HZ` = 1, 10, 50 Hz uniquement.
Si écart > `CAL_DAILY_TOL_DB` = 0,5 dB vs étalonnage de référence
→ déclencher un étalonnage complet.

## Traçabilité

- Accéléromètre de référence calibré NRC Canada (ISO/IEC 17025).
- Conserver le certificat dans `docs/calibration_certificates/`.
- Chaque export de calibration trace le modèle de géophone (en-tête CSV /
  clé NPZ) et la date.

## État d'implémentation

| Étape | Module | Statut |
|-------|--------|--------|
| Enveloppe / stiffness / ZER | `aps/shaker_physics.py`, `testbench.py` | ✅ |
| Servo amplitude boucle fermée | `testbench.py` | ✅ |
| Détection cohérente (amplitude) | `dsp.py` | ✅ |
| `H_banc(f)` (transfert banc) | `testbench.py` | ✅ |
| Plancher de bruit / SNR | `dsp.py`, `testbench.py` | ✅ |
| THD | `dsp.py` | ✅ |
| Sensibilité géophone (sweep) | `testbench.py`, `gui.py` | ✅ |
| Linéarité (3 niveaux × N fréq.) | `testbench.py`, `gui.py` | ✅ |
| Vérification quotidienne (vs réf.) | `testbench.py`, `gui.py` | ✅ |
| Campagne 2 axes (automatique) | `gui.py` | ✅ |
| Sensibilité transversale (cross-axis) | `gui.py` | ✅ |
