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
2. **Fonction de transfert du banc `H_banc(f)`** — grille log (défaut GUI
   0,1–50 Hz), **sans géophone monté**. Pour chaque f : enveloppe → cible →
   stiffness adaptée → servo amplitude → mesure `a_table`. Comme aucun géophone
   n'est monté, la limite de vitesse est désactivée (`bench_transfer_ignore_velocity`)
   → excitation à pleine amplitude (course/plafond g) pour maximiser le SNR.
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

## Enveloppe d'excitation (déplacement / vitesse / accélération)

L'accélération cible par fréquence est l'intersection de trois limites
(`equipment/aps/shaker_physics.py`, `target_accel_g`) :

```
cible = min( fraction·a_max(f) ,  v_max·2πf/g ,  accel_cap_g )
            déplacement (bas f)   vitesse (mid)   accel (haut f)
```

- **Vitesse — anti-saturation du géophone.** Le géophone sort une tension ∝ vitesse ;
  sa sortie doit rester sous la pleine échelle ADS1285 (±2,5 V à gain 1). `v_max` est
  calculé **par géophone** (`equipment/geophones.py`) :

  ```
  v_max = safety · V_pleine_échelle / (G · |H|_max),   |H|_max = 1/(2ζ·√(1-ζ²))
  ```

  où `|H|_max` borne le **pic de résonance** d'un géophone sous-amorti (ex. HG-5VHS,
  ζ=0,268 → ×1,94, qui sature près de `f0` alors que la bande plate semble OK).
  Effet : balayage à **vitesse constante** dans la bande utile, sortie géophone bornée
  (50 % de la pleine échelle au pic par défaut, `geophone_velocity_safety`).
- **Plancher** : un point est ignoré si `cible < accel_floor_g` (défaut 0,0002 g, bas
  pour autoriser les géophones sensibles aux très basses fréquences ; la qualité réelle
  est signalée par le SNR).
- **H_banc / vérif. quotidienne** : limite de vitesse désactivée (aucun géophone monté).

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
- **Sauvegarde automatique** : chaque acquisition/calibration écrit dans `data/`
  un fichier nommé par cas et horodaté (`<cas>[_<géophone>][_<axe>]_<date>_<heure>`),
  avec en-tête de métadonnées (géophone, date, knobs APS 125, plancher de bruit). Le
  **balayage** s'écrit **incrémentalement** : CSV de table complété à chaque point,
  un fichier d'ondes brutes par point `onde_<géo>_<axe>_<freq>Hz_<ts>.npz`, puis en
  fin de séquence l'ajustement `(G0, f0, ζ)` (CSV) et un NPZ résumé. Un échec
  d'acquisition d'un point est réessayé une fois puis le point est ignoré (la
  séquence continue). Journal : `logs/bench_<date>_<heure>.log` (un par session).

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
| Plafond de vitesse anti-saturation par géophone | `geophones.py`, `shaker_physics.py` | ✅ |
| Ajustement réponse géophone (G0, f0, ζ) + comparaison | `dsp.py`, `gui.py` | ✅ |
| Sauvegarde automatique horodatée (CSV + NPZ par cas) | `datastore.py`, `gui.py` | ✅ |
