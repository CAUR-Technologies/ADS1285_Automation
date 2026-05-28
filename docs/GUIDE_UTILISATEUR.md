# Guide utilisateur — Banc d'étalonnage de géophones

Mode d'emploi pas-à-pas pour l'opérateur. Pour la théorie métrologique, voir
[`CALIBRATION_PROTOCOL.md`](CALIBRATION_PROTOCOL.md) ; pour l'architecture
logicielle, voir [`../CLAUDE.md`](../CLAUDE.md).

---

## 1. À qui s'adresse ce guide

À toute personne qui exploite le banc pour **caractériser la réponse en
fréquence d'un géophone** (0,1–100 Hz), sans avoir à toucher au code.

## 2. Le banc en bref

```
Wavetek ─► APS 0109 (contrôleur position, +offset DC) ─► APS 125 (ampli) ─► Shaker APS 113
                                                                               │
                                          ┌────────────────────────────────────┤
                                   accéléromètre de référence            géophone testé
                                   (NI USB-6221)                         (carte ADS1285)
```
Deux chaînes indépendantes existent : **axe Vertical (V)** et **axe Horizontal (H)**,
chacune avec son shaker, son ampli APS 125 et son **accéléromètre de référence**
(canal NI dédié, ex. ai0=V, ai1=H). Un **seul Wavetek** alimente les deux chaînes
via un **splitter** (amplitude commune ; chaque axe est dosé par le gain de son
APS 125). Aucun re-routage manuel n'est nécessaire entre les axes.

## 3. ⚠️ Règles de sécurité (à lire avant toute manipulation)

- **Ne jamais modifier les knobs de l'APS 125 pendant un étalonnage.** Tout
  changement rend l'étalonnage invalide (l'ampli est manuel : le logiciel ne
  peut pas le savoir, c'est pourquoi vous saisissez la valeur du knob).
- **Centrage ZER obligatoire avant tout signal** : l'armature doit être centrée.
- **Basse fréquence = grand déplacement.** Le logiciel plafonne l'amplitude pour
  rester dans la course (±38 mm), mais ne forcez jamais une amplitude manuelle élevée.
- En cas d'**overtravel** (butée), le logiciel coupe automatiquement l'excitation
  et interrompt la séquence. Vérifiez le montage avant de relancer.
- Le bouton **Arrêter** (barre d'actions) interrompt proprement un balayage.

## 4. Préparation matérielle

1. **Montage.** L'accéléromètre de référence est fixé sur l'**armature** du shaker
   (à demeure). Pour la **caractérisation du banc** (plancher de bruit, transfert
   banc `H_banc`), **aucun géophone n'est monté** — on excite à pleine amplitude.
   Pour le **balayage / linéarité / transversale**, monter le géophone sur son
   **support**, bien couplé et orienté selon son axe sensible. (Le Wavetek est déjà
   routé aux deux chaînes par le splitter — pas de câble à déplacer.)
2. **Régler les knobs de l'APS 125** de chaque axe utilisé et **noter leurs
   valeurs** (à saisir dans le logiciel) :
   - **Variable Gain (dB)** : fixe l'amplitude de sortie → définit la réponse
     du banc (`H_banc`). Knob d'étalonnage principal.
   - **Current Limit (A RMS)** : protection de la bobine. À régler assez **haut**
     pour ne pas écrêter aux points exigeants (haute fréquence / 1 g) sans
     dépasser le courant nominal du shaker. Tracé pour la traçabilité et le
     diagnostic d'écrêtage (n'entre pas dans le calcul).
3. Mettre sous tension : APS 0109 (V et H), APS 125 (V et H), Wavetek, carte
   ADS1285, boîtier NI.

> Le panneau « onglets » inclut aussi **Linéarité**. La barre du bas affiche les
> indicateurs de connexion et le statut.

## 5. Démarrer le logiciel

```bash
python gui.py
```
La fenêtre « ADS1285 Automation » s'ouvre : panneau de gauche = appareils +
calibration, panneau de droite = graphes (onglets **Temporel / FFT / Balayage /
Transfert banc / Linéarité / Transversale / Comparaison**), barre du bas =
indicateurs de connexion + statut.

## 6. Connecter les appareils

Dans le panneau de gauche, pour chacun, cliquer **Connecter** :
- **ADS1285 EVM** : l'init (FPGA + PSM) prend ~15 s (barre animée). Le bouton
  **Tester ADC** permet de vérifier la liaison (valeur ≈ 1868 au repos).
- **Wavetek 39A** : port COM.
- **APS — Table de vibration** : choisir l'**Axe** (Vertical/Horizontal) avec le
  bouton radio (**Horizontal par défaut**), renseigner le **port du contrôleur**,
  cliquer **Connecter**. Saisir le **Gain (dB)** et la **Limite courant (A RMS)**
  de l'APS 125 notés à l'étape 4.2.
- **Accéléromètre NI** : device + canaux.

> Les deux contrôleurs (V et H) peuvent rester connectés en même temps ; le
> port et les knobs APS 125 (gain, limite) suivent l'axe sélectionné et sont
> chargés sur l'axe par défaut dès l'ouverture.

## 7. Procédure d'étalonnage (pour l'axe sélectionné)

Section **Calibration banc** (panneau gauche) + barre d'actions.

| Étape | Action | But |
|------|--------|-----|
| 7.1 | Sélectionner le **Géophone** dans la liste | tracé dans les résultats **+ fixe le plafond de vitesse** (anti-saturation, voir §7 bis) |
| 7.2 | **Centrage ZER** | centre l'armature (sans signal) |
| 7.3 | **Plancher bruit** (champ « Bruit (s) », défaut 60) | bruit de fond, shaker arrêté |
| 7.4 | **Transfert banc (H_banc)** — sans géophone monté | caractérise le banc : `H_banc(f)=a/V` [g/V] |
| 7.5 | **Balayage** — géophone monté | mesure la **sensibilité du géophone** (counts/g) |
| 7.6 | **Linéarité** (optionnel) | sensibilité à 3 niveaux × N fréq. (onglet Linéarité), tolérance 1 dB |

> **Sauvegarde automatique.** Chaque acquisition et chaque calibration écrit
> automatiquement ses fichiers dans `data/`, nommés par cas et horodatés (ex.
> `balayage_HG-5VHS_horizontal_2026-05-28_14-25-59.csv` + `.npz`,
> `transfert_banc_horizontal_…csv`, `plancher_bruit_…`, `acquisition_…`). Le bouton
> **Sauvegarder** reste disponible pour un export manuel ponctuel. Tous les échanges
> instruments sont journalisés dans `logs/bench_<date>_<heure>.log` (un par session).

**Définir une référence** (pour la vérification quotidienne) : après un bon
**Transfert banc**, cliquer **Définir réf.** — le H_banc de l'axe est enregistré
dans `reference/h_banc_<axe>.json`.

Réglages communs (avant 7.4/7.5) :
- **Fréquences** (barre d'actions) : liste séparée par virgules, défaut `0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50` (grille log)
- **Fraction env.** : fraction de la course utilisée (défaut 0,6 = marge de sécurité)
- **Plafond (g)** : accélération max en haute fréquence (défaut 1 g)
- **Taux (SPS)** et **Nb échantillons** : acquisition du géophone (ADS1285)

Pendant un balayage, la barre de statut affiche par fréquence : g mesuré,
stiffness appliquée, déplacement, marge de sécurité (ou SNR/THD pour H_banc).

## 7 bis. Enveloppe d'excitation et anti-saturation du géophone

À chaque fréquence, le logiciel choisit l'**accélération cible** comme le minimum
de trois limites :

```
cible = min( fraction·a_max(f)  ,  v_max·2πf/g  ,  plafond_g )
            déplacement (bas f)    vitesse (mid)   accel (haut f)
```

- **Déplacement** : rester dans la course mécanique (±38 mm).
- **Vitesse** : un géophone sort une tension ∝ **vitesse** ; on borne la vitesse
  pour que sa sortie ne sature pas l'ADS1285. `v_max` est **calculé par géophone**
  (sensibilité, amortissement, pic de résonance) — voir `equipment/geophones.py`.
  Concrètement le balayage devient un **balayage à vitesse constante** dans la bande
  utile (sortie géophone uniforme, pas d'écrêtage).
- **Accélération** : plafond de sécurité (défaut 1 g).

**Transfert banc / vérification quotidienne** : comme **aucun géophone n'est monté**,
la limite de vitesse est **désactivée** (réglage `bench_transfer_ignore_velocity` dans
`config.ini`, `true` par défaut) → excitation à pleine amplitude pour un meilleur SNR
de `H_banc`. Le journal l'indique au démarrage du transfert banc.

> Si tu changes de géophone, **re-sélectionne-le** : le plafond de vitesse (et donc
> l'amplitude d'excitation) en dépend.

> **À refaire une seule fois par configuration** : 7.3 (bruit) et 7.4 (H_banc)
> caractérisent le **banc** (par axe). **À refaire pour chaque géophone** : 7.5.

## 8. Étalonner les deux axes

Comme le splitter alimente les deux chaînes et que chaque axe a son propre
accéléromètre de référence (canal NI dédié), le logiciel bascule d'axe en
interne — **aucune manipulation physique entre V et H**.

**Option A — manuelle :** cocher l'autre **Axe**, vérifier son **Gain APS 125**,
puis refaire 7.2 → 7.5.

**Option B — campagne automatique :** cliquer **Campagne 2 axes auto (V+H)**.
Le logiciel étalonne V puis H d'affilée (centrage ZER + balayage par axe), sans
intervention. Nécessite les **deux contrôleurs APS connectés** et les gains
APS 125 des deux axes saisis.

> ⚠️ Le Wavetek pilotant les deux shakers en parallèle, l'axe non mesuré vibre
> aussi. C'est sans effet sur la mesure (on lit l'accéléromètre de l'axe
> courant), mais assurez-vous que rien n'est en sur-course sur l'axe inactif.

Les résultats des deux axes **coexistent** : les graphes **Balayage** et
**Transfert banc** superposent V (bleu) et H (rouge). Une seule **Sauvegarde**
contient les deux axes.

## 8 ter. Sensibilité transversale (cross-axis)

Cliquer **Transversale (cross-axis)**. Le logiciel :
1. excite **le long** de l'axe sensible (géophone sur le shaker de son axe) et
   mesure `S_main` ;
2. affiche une **pause** : remonter le géophone sur l'autre shaker, **axe sensible
   perpendiculaire** au mouvement ;
3. excite **perpendiculairement** et mesure `S_trans`.

Résultat : `S_trans / S_main × 100` (%) vs fréquence (onglet **Transversale**),
seuil **5 %**. L'axe non excité est mis au silence automatiquement (STP).

## 8 bis. Vérification quotidienne

Avant une journée de mesures, sur chaque axe ayant une référence : cliquer
**Vérif. quotid.** Le logiciel mesure H_banc à 1/10/50 Hz et compare à la
référence. Si l'écart max dépasse **0,5 dB**, une alerte demande de refaire
l'étalonnage complet du banc.

## 9. Lire les résultats

**Onglet Balayage** : réponse du géophone vs fréquence (V + H superposés). Un
sélecteur **Affichage** propose trois représentations :
- **counts/g (brut)** : la mesure directe ;
- **counts/(m/s) (vitesse)** : convertit en sensibilité de vitesse (retire le
  facteur 1/f) — c'est la vraie réponse du géophone (plate au-dessus de `f0`) ;
- **Normalisé (/G0)** : divisé par la bande plate, pour comparer les formes.

En modes vitesse/normalisé, le **modèle géophone 2ᵉ ordre ajusté** est superposé et
la légende affiche `(f0, ζ)`. L'ajustement `(G0, f0, ζ)` est aussi écrit dans le
fichier de sortie (≥ 4 points requis).

**Onglet Transfert banc** : `H_banc(f)` (g/V) vs fréquence, V + H.

**Onglet Comparaison** : bouton **Charger des balayages…** → superpose plusieurs
fichiers `balayage_*.npz` (réponses normalisées ou en vitesse), chaque courbe
annotée de son `f0/ζ`. Sert à comparer correctement des géophones de sensibilités
différentes.

**Fichier CSV (balayage)** : en-tête de métadonnées (`# geophone`, `# date`, `# axis`,
`# aps125_gain_*`, `# noise_floor_*`, et l'ajustement `# fit_G0_counts_per_mps`,
`# fit_f0_hz`, `# fit_zeta`, `# fit_rms_error_db`) ; puis une ligne par point avec
colonnes `axis, aps125_gain, aps125_current_limit, freq_hz, target_g, measured_g,
vpp, stiffness, displacement_mm, peak_velocity_mps, safety_margin_mm, snr_db,
thd_percent, geophone_counts_peak, sensitivity_counts_per_g, skipped, note,
sensitivity_counts_per_mps`.

**Fichier NPZ (balayage)** : métadonnées (`geophone_model`, `date`, `aps125_*`,
`noise_floor_*`), `axis`, `freq_hz`, les colonnes de résumé `summary_*` (dont
`summary_sensitivity_counts_per_mps` et `summary_sensitivity_normalized`),
l'ajustement `fit_G0_counts_per_mps / fit_f0_hz / fit_zeta / fit_rms_error_db`, et
les **formes d'onde brutes par fréquence** `geo_wave_<f>Hz` / `accel_wave_<f>Hz`
(données temporelles, pour ré-analyse). Les autres cas (acquisition, linéarité,
plancher de bruit) ont leurs propres fichiers analogues.

## 10. Quand refaire l'étalonnage complet du banc

- Knobs de l'APS 125 modifiés
- Accéléromètre de référence remplacé
- Banc déplacé physiquement
- Écart > 1 dB lors d'une vérification

## 11. Dépannage

| Symptôme | Cause probable / solution |
|---|---|
| « non connecté : … » au lancement d'un balayage | Connecter Wavetek + APS (axe) + accéléromètre |
| Carte ADS1285 figée / USB-13 | Débrancher/rebrancher l'USB de l'EVM, reconnecter |
| Bridge 32-bit ne répond pas | Vérifier `bridge/fpga_*.bin` et les binaires PSM présents |
| Signal géophone = bruit | Vérifier couplage/orientation ; **Tester ADC** ; mode acq. PSM |
| Overtravel répété | Amplitude trop forte en basse fréquence : baisser Fraction env. / Plafond, vérifier ZER |
| SNR faible noté dans le statut | Normal en très basse fréquence ; augmenter Nb cycles (code) ou amplitude si la course le permet |
| « Module nidaqmx non trouvé » | Installer NI-DAQmx Runtime + `pip install nidaqmx` |
