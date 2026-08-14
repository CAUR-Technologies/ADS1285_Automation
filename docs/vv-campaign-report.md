# Rapport de campagne V&V — enregistreur géophone CAUR (2026-08)

Rapport complet de vérification & validation : acceptation flotte, caractérisation
métrologique, validation banc/instrumentation, et investigations de cause racine.
Firmware de test uniforme **`0.1.0.211 / dae370c+`** (branche `gp/fix-cdc-get-large-tx`,
config `test-bench.conf`), flashé sur les 9 prototypes par USB DFU.

## 1. Verdict

**GO 🟢.** Les **8 unités config-production** passent l'acceptation : **7 PASS, 1 WARN,
0 FAIL** + checklist manuelle. Aucun défaut de **design** bloquant. La 9ᵉ (CG0-000008)
est **exclue** (board modifié — résistances d'entrée retirées). Les écarts relevés sont
des **correctifs firmware** (backlog), pas des défauts matériels. Le **bruit propre de la
chaîne ADC est validé vs la fiche ADS1285** (±11 % sur 4 gains, §5.2). Seul **V14 (watchdog)**
reste vraiment non couvert (trou firmware, §7) ; V3 et V5 sont caractérisés (voir §7). Aucun
de ces points ne conditionne le go/no-go design.

## 2. Périmètre & méthode

- **Acceptation automatisée** — `tools/acceptance.py` (USB seul, sans shaker, ~2 min/unité) :
  V1/V13/V6/CFG/V11/V7/V2/V8. Freeze-robuste (chaque commande sous timeout).
- **Checklist manuelle** : V9 (USB-MSD), V10 (LEDs), V15 (enregistrement réel au bouton).
- **Bruit propre ADC (ACQ-09)** : entrées court-circuitées, 4 gains, PSD Welch vs fiche
  ADS1285 (§5.2 ; doc produit `bruit-plancher-v31.md`).
- **Caractérisation métrologique** (banc shaker+GNSS+accéléro réf. NI) : réponse en
  fréquence des géophones — 3 axes (§5) + campagne 8 géophones mono-axe (§5.3).
- **Validation banc/instrumentation** : 1PPS, GNSS, corrélation temporelle (TIME-05),
  holdover PPS (§6).

## 3. Matrice de validation V1–V15

| Test | Objet | Statut | Méthode / résultat |
|---|---|---|---|
| **V1** | Boot & console | ✅ PASS (8) | STATUS ×3, uptime monotone, pas de reboot |
| **V2** | ADS1285 ×3 | ✅ PASS (8) | 3 voies vivantes, non figées ; ADC exercé à fond en caractérisation (§5) |
| **V3** | Synchro ADC (≤1 éch.) | 🟡 **partiel** | **firmware aligne les 3 voies** (horodatage inter-voies = **0,000 éch** sur fichiers propres, `tools/v3_sync.py`) ; synchro ADC **physique** ≤1 éch **non prouvée** par le tap (confond la mécanique des 3 axes) → injection électrique commune requise (§7) |
| **V4** | GNSS (fix + 1PPS) | ✅ PASS | unité LC86G : `fix=1`, 4–7 sats, position Montréal ; ProPak 1PPS sur PFI0 = 0,99 Hz |
| **V5** | Horodatage (dérive/PPS) | 🟡 **partiel** | cadence **250,07 Hz stable**, horodatage RTC/PPS suit l'UTC record/record (pas de dérive) ; **plancher = 3,9 ms** (quantif. RTC 1/256 s) → cause racine du bruit TIME-05, fix prescaler RTC (`tools/pps_stability.py`, §6) |
| **V6** | IMU | ✅ PASS (8) | STREAM, \|g\| ≈ 1,00 (0,8–1,2) |
| **V7** | µSD / transfert | ✅ PASS (8) | 3 voies écrites+relues ; corruption **en transit CDC uniquement** (§8.6), SD intacte, ~180–220 Ko/s |
| **V8** | MiniSEED | ✅ PASS (8) | fichiers valides (simplemseed v3 ; ObsPy = v2 only, non applicable) |
| **V9** | USB (MSD + CDC) | ✅ PASS | manuel : disque de masse monte ; CDC utilisé de bout en bout |
| **V10** | LEDs WS2812 | ✅ PASS | manuel : 4 pixels répondent ; mapping documenté (§8.5, D13 = Health) |
| **V11** | Tension batterie | 🟡 PASS (plage) | lecture dans la plage, MAIS **jauge fausse** (sous-estime + glitches, §8.3) |
| **V12** | BLE | ✅ **PASS** | contrôleur BLE **monté sur toutes** ; advertising visible **+ app companion fonctionnelle** (transport, GATT, contrôle validés) |
| **V13** | Détection révision (MAX7319) | ✅ PASS (8) | `hwrev: 1` sur toutes |
| **V14** | Watchdog / RTC | ⛔ **ABSENT (trou FW)** | **aucun watchdog dans le firmware** (vérifié : pas de `CONFIG_WATCHDOG`/`wdt_feed`) → gels = reset manuel obligatoire (§8.4, backlog #7) |
| **V15** | Acquisition E2E | ✅ PASS | manuel (record bouton) + auto (transfert/parse) : miniSEED 3 voies daté GNSS, valide |
| — | **CFG** (config USB) | ✅ PASS (8) | CONFIG SET/GET aller-retour |

Légende : ✅ couvert PASS · 🟡 couvert avec réserve · ⛔ non couvert · ➖ non applicable.

## 4. Résultats acceptation flotte (8 unités config-production)

| Unité | Overall | V1 | V13 | V6 | CFG | V11 | V7 | V2 | V8 |
|---|---|---|---|---|---|---|---|---|---|
| CG0-000001 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000002 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000003 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000004 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000005 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000006 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000007 | PASS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CG0-000009 | WARN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ⚠ | ✓ |

**7 PASS · 1 WARN · 0 FAIL.** 009·V2 = saturation d'un *ancien* enregistrement à forte
amplitude testé (l'amplitude reflète le run, pas la santé de la voie — non un défaut).
Résultats bruts : `data/acceptance/*.json` (`python tools/acceptance.py --fleet`).

## 5. Caractérisation métrologique (calibration — hors périmètre V&V produit)

Réponse en fréquence 3 axes de CG0-000009 (banc shaker APS + accéléro de réf. NI),
0,2–100 Hz, corrélation par segmentation :

| Axe | voie | plateau V/(m/s) | pic (résonance) | ζ |
|---|---|---|---|---|
| X | ch1 | ~160 | ~234 @ 4–5 Hz | 0,41 |
| Y | ch2 | ~160 | ~250 @ 4–5 Hz | 0,37 |
| Z | ch3 | ~157 | **~510 @ 5–6 Hz** | 0,23 |

Géophone **UHS confirmé** ; Z nettement plus haut-Q (répété 2×, écarts ≤ 8 %). Plateau
homogène ~155–160 sur les 3 axes → chaîne de mesure saine. *La diffusion pour l'ANT
(StationXML pôles/zéros + convention SID FDSN, DATA-07) reste à cadrer avec le géophysicien.*

> ⚠️ **Convention de pleine échelle à trancher (impacte ces sensibilités).** `equipment/
> geophone3axis/dat_reader.py` convertit les counts avec **±2,5 V** à gain 1 (validé par la
> sensibilité ST-2A 265 vs 260). Or le rapport de bruit produit (§5.2) valide **±VREF/2 =
> ±2,048 V** par la concordance au **bruit datasheet** (±11 % sur 4 gains) — évidence plus
> directe. Facteur **1,22** : si 2,048 V est correct, les plateaux ci-dessus tombent à
> ~128–131. **À résoudre sur la fiche ADS1285** (FSR ±VREF/2 vs ±VREF/1,6384) avant toute
> diffusion de sensibilité absolue.

## 5.2 Bruit propre de la chaîne d'acquisition (ACQ-09) — ADS1285

Validation du **bruit propre de l'électronique** (ADC + PGA), **entrées court-circuitées**
(MUX ADS1285 en court, 400 Ω, aucun géophone), sur CG0-000006 — le test « design vs fiche
ADS1285 ». 4 gains, 634–708 s, PSD Welch moyennée sur les 3 voies, comparé à la table 6-1
de la fiche. *Doc canonique : `geophones-product/docs/bruit-plancher-v31.md`.*

| Gain | Bruit mesuré | Fiche ADS1285 | Écart | Dynamique mesurée |
|---|---|---|---|---|
| **1** | **0,271 µVrms** | 0,25 | +8 % | **134,6 dB (22,1 bits)** |
| 2 | 0,156 | 0,14 | +11 % | 133,3 dB |
| 8 | 0,064 | 0,07 | −9 % | 129,0 dB |
| 16 | 0,054 | 0,06 | −10 % | 124,4 dB |

**Verdict : ✅ PASS — la chaîne se comporte comme le composant l'annonce** : les 4 gains
collent à la fiche à **±11 %**, aucun bruit parasite ajouté par la carte (non trivial sur un
1ᵉʳ proto). Les 3 voies sont équivalentes à quelques %. Bruit **1/f classique** (pente
f^−0,44 mesurée), coude passant de **3,23 Hz (g1) à 0,15 Hz (g16)**.

**Point d'attention ANT** : la bande **0,1–1 Hz** est entièrement en zone 1/f (bruit ×3–8
vs plancher) — là où le géophone produit le moins. Le **gain corrige largement** (÷10–12 à
g16, coude à 0,15 Hz) au prix de la pleine échelle (±128 mV). **Choix du gain de production
ouvert** (ACQ-09) : gain 2 quasi gratuit (−1,2 dB), gain 16 le moins bruyant en bande ANT ;
à trancher sur l'amplitude géophone max. *(Note : mesure faite sans géophone — à refaire
capteur raccordé pour la chaîne complète.)*

## 5.3 Campagne de calibration géophones (banc mono-axe V/H)

**8 géophones** caractérisés en fréquence 0,1–100 Hz sur les **2 axes indépendants**
(2026-06-05→08), `data/rapport_geophones_ALL_2026-06-08/`.

| Géophone | Axe | Sensibilité | Spec | f0 / ζ | Verdict |
|---|---|---|---|---|---|
| ST-2A | V/H | 294 / 272 V/(m/s) | 260 | 3,3 / 5,9 Hz | excellent (datasheet ±5–13 %) |
| HG-6 (XT UB / HB) | V/H | 38 / 36 | 28,8 | 5,4 / 6,5 Hz | conforme (classe HGS) |
| HG-5VHS | V | 118 | 100 | 4,5 / 0,63 | conforme |
| HG-2 U | V | 170 | ~50 (est.) | 3,6 / 0,52 | spec à confirmer |
| VAS-200 / VAS-H-200 | V/H | ≥141 / ≥145 | 220 | anomalie | à rebalayer > 100 Hz |

**Validation croisée** : 3 familles mesurées sur les **deux chaînes V/H totalement séparées**
concordent à **±4 %** (ST-2A 294/272, HG-6 38/36, VAS 141/145) + ST-2A concorde à la
datasheet (+5–13 %) → **métrologie des deux bancs validée**. **Plancher de bruit accéléro
de réf.** : **V = 0,62 mg RMS · H = 0,57 mg RMS** (2026-05-28) — fixe la limite basse
fréquence (sous ~1–2 Hz, SNR < 20 dB : course shaker ±38 mm + plancher + roll-off f² du
géophone ; limite **physique**, non logicielle).

## 6. Validation banc / instrumentation

- **1PPS** : ProPak sur PFI0 de la crate NI = **0,99 Hz** (stable).
- **GNSS** : fix unité (LC86G) et référence (ProPak) confirmés en extérieur/antenne.
- **Corrélation temporelle (TIME-05)** : pipeline matériel **opérationnel** (conflit de
  tâche NI `-50103` résolu par sérialisation ; `tools/time_correlation.py` +
  `tools/time_offset.py`). **Cause racine du bruit IDENTIFIÉE** (`tools/pps_stability.py`,
  run GNSS fixe) : les horodatages `.dat` sont **quantifiés à 3,9 ms (1/256 s)** — la RTC
  STM32 tourne au **prescaler par défaut** (async 127 / sync 255). La cadence est saine
  (**250,073 Hz**, +291 ppm quartz ADC) et suit l'UTC record par record (pas de dérive),
  mais **3,9 ms est le plancher de précision**. **Fix** : prescaler RTC async ~0 / sync
  ~32767 → **~30 µs** (×128), puis re-mesurer TIME-05. *(Backlog FW #8.)* Un **saut
  d'horodatage** occasionnel (~140 ms au démarrage) reste à qualifier.
- **Holdover PPS (V5)** (`tools/v5_holdover.py`, antenne débranchée en cours d'acquisition) :
  RTC en holdover → **dérive ~16 ppm (~1,4 s/jour)** sur le LSE seul (cohérent quartz montre).
  **Discipline sous PPS** : pas de dérive tant que le fix tient (cadence collée à l'UTC). Le
  **saut de recalage** à la reprise du fix n'a **pas encore été capturé** (warm start > fenêtre,
  puis coupure batterie) → à reconfirmer, batterie chargée, 3 min après rebranchement.

## 7. Couverture — tests NON réalisés

- **V3 (synchro inter-voies ≤ 1 échantillon)** : **partiel** (`tools/v3_sync.py`, tap sur
  CG0-000006, 2026-08-14). Acquis : le **firmware horodate les 3 voies à l'identique**
  (0,000 éch sur 3 fichiers propres). Le **tap ne peut pas** trancher la synchro ADC
  physique sous-échantillon car les 3 axes filtrent le choc différemment (démontré :
  voies 1 & 3 même en-tête mais enveloppes décalées de 1,7 éch = **mécanique pure**).
  **Reste** : injecter le **même signal électrique dans les 3 entrées ADC** (Wavetek
  splitté ; board 008 aux entrées accessibles) → cross-corrélation isole le seul décalage
  d'échantillonnage. *(Un décalage physique traduirait un défaut de portage de la ligne
  SYNC PD4 dans `geophone.dts`.)*
- **V5 (dérive horloge / recalage PPS)** : **bien caractérisé, partiel** — cadence stable
  (250,07 Hz, suit l'UTC), holdover ~16 ppm mesuré, plancher 3,9 ms identifié (§6) ; reste à
  **capturer visuellement le recalage** à la reprise du fix (batterie chargée + 3 min d'attente).
- **V14 (watchdog / RTC au reboot)** : **watchdog ABSENT du firmware** (vérifié — aucun
  `CONFIG_WATCHDOG`/`CONFIG_TASK_WDT`/`wdt_feed`). C'est un **trou firmware**, pas une simple
  lacune de test : les gels observés (§8.4) ont exigé un **reset manuel** faute d'auto-reset.
  À implémenter (backlog FW #7, priorité haute) puis tester par hang volontaire. *Incohérence :
  la matrice V&V produit marque FW-03 « couvert ».*
- **V12 (BLE)** : **couvert / PASS** — contrôleur monté sur toutes, advertising visible et
  **app companion Bluetooth fonctionnelle** (transport + GATT + contrôle).

## 8. Findings & investigations

Tracés au backlog firmware `geophones-firmware/doc/test-bench-to-production.md` :

1. **TX CDC non-bloquante** (`CDC_LARGE_TX`) → à porter en production (robustesse générale).
2. **START/STOP idempotents BLE** → correctif contrôle app (le BLE reste un toggle).
3. **Jauge batterie fausse (dans les deux sens)** : **sous-estime** en haut (74 % à batterie
   pleine 7,57 VDC) ET **surestime** en bas (a lu `74 %` puis **s'est éteint** faute de charge,
   2026-08-14) + glitches à `1`/`2`. Non fiable → recalibrer + filtrer. **Observation liée** :
   le board **s'est éteint alors que l'USB était branché** → l'**USB ne semble pas alimenter/
   charger** (à rapprocher du gotcha HW J8-USB-sans-GND) → autonomie = batterie seule, prévoir
   un vrai chargeur. *(Backlog FW #3 + à vérifier côté HW.)*
4. **Gel sous charge** : survenu autour de l'**USB-pendant-acquisition** (condition test-only ;
   en prod l'USB préempte l'acquisition). Reset manuel requis (cf. V14). À confirmer non-latent.
5. **Écriture SD** : `open+append+close` par record (durable mais lourd) → keep-open + `fs_sync`
   périodique. `records_per_file` **n'est pas** un levier de sécurité (crash ⇒ ≤ 1 record perdu).
6. **Transfert CDC — corruption EN TRANSIT (prouvé)** : un même `.dat` récupéré **3× →
   3 md5 différents**, corruption à positions différentes/nulle → **le lien USB-CDC** corrompt,
   **la SD est intacte**. ~0,2–0,5 % de records. **Récupérable sans perte par CRC + retry.**

## 9. Conclusion & suites

**GO pour le design** : flotte homogène, saine, aucun FAIL. Suivis :

- **Correctifs firmware** (non bloquants) : jauge batterie + charge/USB (moyen) · BLE idempotent
  (haut) · intégrité+retry transfert CDC (moyen) · TX CDC en prod (moyen) · écriture SD (bas) ·
  **prescaler RTC → 30 µs (haut, débloque TIME-05)** · **watchdog (haut, fiabilité terrain)**.
- **Résoudre la convention de pleine échelle ADC** (±2,048 V vs ±2,5 V, §5.1) — impacte les
  sensibilités 3 axes ; trancher sur la fiche ADS1285 avant diffusion.
- **Compléter la couverture** : V3 (injection électrique), V5 (capturer le recalage PPS),
  V14 (implémenter le watchdog).
- **Choix du gain de production** (ACQ-09, §5.2) : arbitrer bruit BF vs pleine échelle sur
  l'amplitude géophone max (mesure capteur raccordé).
- **CG0-000008** : rétablir la config prod puis ré-accepter, ou statuer « exclu ».
- **Calibration ANT** : StationXML + convention SID (DATA-07) avec le géophysicien.

---
*Généré à partir des résultats `data/acceptance/*.json`, de la caractérisation
`data/3axis/`, et du backlog `geophones-firmware/doc/test-bench-to-production.md`.
Voir aussi `docs/go-no-go-report.md` (synthèse décision) et `docs/acceptance-fleet.md`
(procédure).*
