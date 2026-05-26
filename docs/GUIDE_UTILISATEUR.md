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
chacune avec son shaker et son ampli APS 125. Un **seul Wavetek** alimente une
chaîne à la fois.

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

1. **Monter le géophone** sur l'armature du shaker de l'axe à tester (V ou H),
   bien couplé et orienté selon son axe sensible.
2. **Router le signal Wavetek** vers la chaîne de l'axe choisi (entrée Signal In
   de l'APS 0109 correspondant).
3. **Régler les knobs de l'APS 125** de cet axe (gain) à la valeur voulue, et
   **noter cette valeur** — vous la saisirez dans le logiciel.
4. Mettre sous tension : APS 0109, APS 125, Wavetek, carte ADS1285, boîtier NI.

## 5. Démarrer le logiciel

```bash
python gui.py
```
La fenêtre « ADS1285 Automation » s'ouvre : panneau de gauche = appareils +
calibration, panneau de droite = graphes (onglets **Temporel / FFT / Balayage /
Transfert banc**), barre du bas = indicateurs de connexion + statut.

## 6. Connecter les appareils

Dans le panneau de gauche, pour chacun, cliquer **Connecter** :
- **ADS1285 EVM** : l'init (FPGA + PSM) prend ~15 s (barre animée). Le bouton
  **Tester ADC** permet de vérifier la liaison (valeur ≈ 1868 au repos).
- **Wavetek 39A** : port COM.
- **APS — Table de vibration** : choisir l'**Axe** (Vertical/Horizontal) avec le
  bouton radio, renseigner le **port du contrôleur**, cliquer **Connecter**.
  Saisir le **Gain (knob) APS 125** noté à l'étape 4.3.
- **Accéléromètre NI** : device + canaux.

> Les deux contrôleurs (V et H) peuvent rester connectés en même temps ; le
> champ Gain et le port suivent l'axe sélectionné.

## 7. Procédure d'étalonnage (pour l'axe sélectionné)

Section **Calibration banc** (panneau gauche) + barre d'actions.

| Étape | Action | But |
|------|--------|-----|
| 7.1 | Sélectionner le **Géophone** dans la liste | tracé dans les résultats |
| 7.2 | **Centrage ZER** | centre l'armature (sans signal) |
| 7.3 | **Plancher bruit** (champ « Bruit (s) », défaut 60) | bruit de fond, shaker arrêté |
| 7.4 | **Transfert banc (H_banc)** | caractérise le banc : `H_banc(f)=a/V` [g/V] |
| 7.5 | **Balayage** | mesure la **sensibilité du géophone** (counts/g) |
| 7.6 | **Sauvegarder** | export CSV ou NPZ |

Réglages communs (avant 7.4/7.5) :
- **Fréquences** (barre d'actions) : liste séparée par virgules, ex. `0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100`
- **Fraction env.** : fraction de la course utilisée (défaut 0,6 = marge de sécurité)
- **Plafond (g)** : accélération max en haute fréquence (défaut 1 g)
- **Taux (SPS)** et **Nb échantillons** : acquisition du géophone (ADS1285)

Pendant un balayage, la barre de statut affiche par fréquence : g mesuré,
stiffness appliquée, déplacement, marge de sécurité (ou SNR/THD pour H_banc).

> **À refaire une seule fois par configuration** : 7.3 (bruit) et 7.4 (H_banc)
> caractérisent le **banc** (par axe). **À refaire pour chaque géophone** : 7.5.

## 8. Étalonner le second axe

1. Couper la sortie, **router le Wavetek** vers l'autre chaîne, remonter le
   géophone sur l'autre shaker.
2. Régler/noter les **knobs APS 125** de cet axe.
3. Dans le GUI : cocher l'autre **Axe**, saisir son **Gain**, connecter son
   contrôleur, puis refaire 7.2 → 7.5.

Les résultats des deux axes **coexistent** : les graphes **Balayage** et
**Transfert banc** superposent V (bleu) et H (rouge). Une seule **Sauvegarde**
contient les deux axes.

## 9. Lire les résultats

**Onglet Balayage** : sensibilité géophone (counts/g) vs fréquence, V + H.
**Onglet Transfert banc** : `H_banc(f)` (g/V) vs fréquence, V + H.

**Fichier CSV** : en-tête avec `# geophone`, `# date`, `# aps125_gain_vertical/horizontal` ;
puis une ligne par point avec colonnes `axis, aps125_gain, freq_hz, target_g,
measured_g, vpp, stiffness, displacement_mm, safety_margin_mm, snr_db,
thd_percent, geophone_counts_peak, sensitivity_counts_per_g, skipped, note`.

**Fichier NPZ** : `geophone`, `aps125_gain_vertical/horizontal`, et par axe
`vertical_sweep_*`, `horizontal_sweep_*`, `*_hbench_freq`, `*_hbench_g_per_v`.

## 10. Vérification quotidienne

Avant une journée de mesures : lancer un **Transfert banc** réduit à
**1, 10, 50 Hz**. Si l'écart avec l'étalonnage de référence dépasse **0,5 dB**,
refaire l'étalonnage complet du banc (étapes 7.3–7.4).

## 11. Quand refaire l'étalonnage complet du banc

- Knobs de l'APS 125 modifiés
- Accéléromètre de référence remplacé
- Banc déplacé physiquement
- Écart > 1 dB lors d'une vérification

## 12. Dépannage

| Symptôme | Cause probable / solution |
|---|---|
| « non connecté : … » au lancement d'un balayage | Connecter Wavetek + APS (axe) + accéléromètre |
| Carte ADS1285 figée / USB-13 | Débrancher/rebrancher l'USB de l'EVM, reconnecter |
| Bridge 32-bit ne répond pas | Vérifier `bridge/fpga_*.bin` et les binaires PSM présents |
| Signal géophone = bruit | Vérifier couplage/orientation ; **Tester ADC** ; mode acq. PSM |
| Overtravel répété | Amplitude trop forte en basse fréquence : baisser Fraction env. / Plafond, vérifier ZER |
| SNR faible noté dans le statut | Normal en très basse fréquence ; augmenter Nb cycles (code) ou amplitude si la course le permet |
| « Module nidaqmx non trouvé » | Installer NI-DAQmx Runtime + `pip install nidaqmx` |
