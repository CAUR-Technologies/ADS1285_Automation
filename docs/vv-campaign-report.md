# Rapport de campagne V&V — enregistreur géophone CAUR (2026-08)

Rapport complet de vérification & validation : acceptation flotte, caractérisation
métrologique, validation banc/instrumentation, et investigations de cause racine.
Firmware de test uniforme **`0.1.0.211 / dae370c+`** (branche `gp/fix-cdc-get-large-tx`,
config `test-bench.conf`), flashé sur les 9 prototypes par USB DFU.

## 1. Verdict

**GO 🟢.** Les **8 unités config-production** passent l'acceptation : **7 PASS, 1 WARN,
0 FAIL** + checklist manuelle. Aucun défaut de **design** bloquant. La 9ᵉ (CG0-000008)
est **exclue** (board modifié — résistances d'entrée retirées). Les écarts relevés sont
des **correctifs firmware** (backlog), pas des défauts matériels. Trois tests (V3, V5,
V14) restent **non couverts** (voir §7) ; ils ne conditionnent pas le go/no-go design.

## 2. Périmètre & méthode

- **Acceptation automatisée** — `tools/acceptance.py` (USB seul, sans shaker, ~2 min/unité) :
  V1/V13/V6/CFG/V11/V7/V2/V8. Freeze-robuste (chaque commande sous timeout).
- **Checklist manuelle** : V9 (USB-MSD), V10 (LEDs), V15 (enregistrement réel au bouton).
- **Caractérisation métrologique** (banc shaker+GNSS+accéléro réf. NI) : réponse en
  fréquence des géophones — *hors périmètre V&V produit* (calibration), documentée §5.
- **Validation banc/instrumentation** : 1PPS, GNSS, corrélation temporelle (TIME-05).

## 3. Matrice de validation V1–V15

| Test | Objet | Statut | Méthode / résultat |
|---|---|---|---|
| **V1** | Boot & console | ✅ PASS (8) | STATUS ×3, uptime monotone, pas de reboot |
| **V2** | ADS1285 ×3 | ✅ PASS (8) | 3 voies vivantes, non figées ; ADC exercé à fond en caractérisation (§5) |
| **V3** | Synchro ADC (≤1 éch.) | ⛔ **NON couvert** | nécessite signal commun + analyse de phase (infra TIME-05 prête) |
| **V4** | GNSS (fix + 1PPS) | ✅ PASS | unité LC86G : `fix=1`, 4–7 sats, position Montréal ; ProPak 1PPS sur PFI0 = 0,99 Hz |
| **V5** | Horodatage (dérive/PPS) | 🟡 **partiel** | pipeline TIME-05 opérationnel ; **précision à régler** (§6) |
| **V6** | IMU | ✅ PASS (8) | STREAM, \|g\| ≈ 1,00 (0,8–1,2) |
| **V7** | µSD / transfert | ✅ PASS (8) | 3 voies écrites+relues ; corruption **en transit CDC uniquement** (§8.6), SD intacte, ~180–220 Ko/s |
| **V8** | MiniSEED | ✅ PASS (8) | fichiers valides (simplemseed v3 ; ObsPy = v2 only, non applicable) |
| **V9** | USB (MSD + CDC) | ✅ PASS | manuel : disque de masse monte ; CDC utilisé de bout en bout |
| **V10** | LEDs WS2812 | ✅ PASS | manuel : 4 pixels répondent ; mapping documenté (§8.5, D13 = Health) |
| **V11** | Tension batterie | 🟡 PASS (plage) | lecture dans la plage, MAIS **jauge fausse** (sous-estime + glitches, §8.3) |
| **V12** | BLE (V3.1) | ➖ N/A | boards V2/V3.0, pas de contrôleur BLE monté |
| **V13** | Détection révision (MAX7319) | ✅ PASS (8) | `hwrev: 1` sur toutes |
| **V14** | Watchdog / RTC | ⛔ **NON couvert** | non testé ; N.B. les gels ont exigé un **reset manuel** (§8.4) — à qualifier |
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

## 6. Validation banc / instrumentation

- **1PPS** : ProPak sur PFI0 de la crate NI = **0,99 Hz** (stable).
- **GNSS** : fix unité (LC86G) et référence (ProPak) confirmés en extérieur/antenne.
- **Corrélation temporelle (TIME-05)** : pipeline matériel **opérationnel** (conflit de
  tâche NI `-50103` résolu par sérialisation ; `tools/time_correlation.py` +
  `tools/time_offset.py`). **Précision d'horodatage NON validée** : résultat = bruit
  (phases dispersées) → alignement sod à régler (étiquetage 1PPS↔NMEA + précision
  d'horodatage firmware). **À reprendre** — clé pour la cross-corrélation ANT multi-stations.

## 7. Couverture — tests NON réalisés

- **V3 (synchro inter-voies ≤ 1 échantillon)** : non testé. Faisable avec le signal commun
  du shaker + analyse de phase (infra TIME-05 prête).
- **V5 (dérive horloge / recalage PPS)** : partiel — lié à TIME-05 (précision non réglée).
- **V14 (watchdog / RTC au reboot)** : non testé. **Point d'attention** : les gels observés
  (§8.4) ont nécessité un **reset manuel** → à vérifier si le watchdog devrait les rattraper.
- **V12 (BLE)** : N/A sur ces boards (contrôleur BLE non monté).

## 8. Findings & investigations

Tracés au backlog firmware `geophones-firmware/doc/test-bench-to-production.md` :

1. **TX CDC non-bloquante** (`CDC_LARGE_TX`) → à porter en production (robustesse générale).
2. **START/STOP idempotents BLE** → correctif contrôle app (le BLE reste un toggle).
3. **Jauge batterie fausse** : sous-estime (74 % à batterie **pleine 7,57 VDC**) + glitches
   à `1`/`2`. Recalibrer + filtrer.
4. **Gel sous charge** : survenu autour de l'**USB-pendant-acquisition** (condition test-only ;
   en prod l'USB préempte l'acquisition). Reset manuel requis (cf. V14). À confirmer non-latent.
5. **Écriture SD** : `open+append+close` par record (durable mais lourd) → keep-open + `fs_sync`
   périodique. `records_per_file` **n'est pas** un levier de sécurité (crash ⇒ ≤ 1 record perdu).
6. **Transfert CDC — corruption EN TRANSIT (prouvé)** : un même `.dat` récupéré **3× →
   3 md5 différents**, corruption à positions différentes/nulle → **le lien USB-CDC** corrompt,
   **la SD est intacte**. ~0,2–0,5 % de records. **Récupérable sans perte par CRC + retry.**

## 9. Conclusion & suites

**GO pour le design** : flotte homogène, saine, aucun FAIL. Suivis :

- **Correctifs firmware** (non bloquants) : jauge batterie (moyen) · BLE idempotent (haut) ·
  intégrité+retry transfert CDC (moyen) · TX CDC en prod (moyen) · écriture SD (bas).
- **Compléter la couverture** : V3 (synchro), V5/TIME-05 (précision horodatage), V14 (watchdog).
- **CG0-000008** : rétablir la config prod puis ré-accepter, ou statuer « exclu ».
- **Calibration ANT** : StationXML + convention SID (DATA-07) avec le géophysicien.

---
*Généré à partir des résultats `data/acceptance/*.json`, de la caractérisation
`data/3axis/`, et du backlog `geophones-firmware/doc/test-bench-to-production.md`.
Voir aussi `docs/go-no-go-report.md` (synthèse décision) et `docs/acceptance-fleet.md`
(procédure).*
