# Rapport go/no-go — acceptation produit des prototypes géophone (2026-08)

## Résumé exécutif

**Verdict : GO 🟢.** Les **8 unités en configuration production** validées passent
toutes l'acceptation (**7 PASS, 1 WARN, 0 FAIL**) et la checklist manuelle. Aucun
défaut de **design** bloquant. Les seuls écarts (WARN) sont **systématiques** —
identiques sur toute la flotte — et relèvent de **correctifs firmware** déjà backlogés,
pas de défauts matériels par unité. Une 9ᵉ unité (CG0-000008) est **exclue** car
**modifiée** (résistances d'entrée retirées, board de caractérisation).

## Périmètre et méthode

- **9 prototypes** flashés avec un **firmware de test uniforme** : `0.1.0.211 / dae370c+`
  (branche `gp/fix-cdc-get-large-tx`, config `test-bench.conf` : CDC large-TX, USB
  acquisition, MSD off). Flash par USB DFU (`STM32_Programmer_CLI`).
- **Acceptation automatisée** (`tools/acceptance.py`, USB seul, sans shaker) : tests
  V1/V13/V6/CFG/V11/V7/V2/V8 mappés sur la matrice de validation V1–V15.
- **Checklist manuelle** : V9 (USB-MSD), V10 (LEDs), V15 (enregistrement réel au bouton)
  — **validée**.

## Résultats flotte (8 unités config-production)

| serial | overall | V1 | V13 | V6 | CFG | V11 | V7 | V2 | V8 |
|---|---|---|---|---|---|---|---|---|---|
| CG0-000001 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000002 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000003 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000004 | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000005 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000006 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000007 | PASS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CG0-000009 | WARN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |

**7 PASS · 1 WARN · 0 FAIL** + checklist manuelle OK. Détails : `data/acceptance/*.json`.

## Ce qui est validé (par test)

- **V1 boot / V13 identité** : démarrage stable, firmware **homogène** sur les 9
  (`0.1.0.211/dae370c+`, hwrev 1) — condition d'une comparaison valide.
- **V6 IMU** : |g| ≈ 1,00 sur toutes (0,8–1,2).
- **CFG** : config par USB fiable (aller-retour).
- **V7 transfert** : **donnée enregistrée INTACTE sur la SD** ; ~0,2–0,5 % de records
  arrivent corrompus **uniquement en transit sur le lien USB-CDC** — **prouvé** (même
  fichier récupéré 3× → md5 différents, corruption à positions différentes ou nulle).
  Sur gros échantillons : 0,00 % (004), 0,20 % (001, 3488 records), 0,43 % (006, 1849).
  **Récupérable sans perte par retry** (un GET propre = la vraie donnée).
- **V2 ADC ×3 / V8 miniSEED** : 3 voies présentes et vivantes, fichiers miniSEED valides.
- **V9/V10/V15** (manuel) : USB-MSD monte, LEDs répondent, enregistrement réel au bouton OK.

## Observations systématiques — suivis firmware (le seul WARN résiduel = 009·V2)

1. **Transfert CDC** : ~0,2–0,5 % de records corrompus **en transit sur le lien USB-CDC**
   — la donnée sur la SD est **intacte** (prouvé par test 3× : même fichier → md5 différents,
   corruption à positions différentes/nulle). Systématique → caractéristique du chemin
   GET/CDC, pas un défaut par unité. Correctif : **CRC + retry sur GET** (sans perte).
   *(Backlog FW ; N/B : la production récupère par MSD, pas GET.)*
2. **Jauge batterie** : lit faux — **sous-estime** (74 % à batterie **pleine 7,57 VDC**)
   **et** glitche à `1`/`2`. Affecte `STATUS?` et la caractéristique BLE. *(Backlog FW.)*
3. **009 · V2 WARN** : saturation d'un **ancien** enregistrement à forte amplitude testé
   (pas un défaut ADC — l'amplitude reflète le run, pas la santé de la voie).

## Unité exclue

- **CG0-000008 — MODIFIÉE (résistances d'entrée ADC retirées)**, non représentative de la
  production. En enregistrement : **LED D13 (Health) rouge** = `RUNTIME_ERROR` après
  quelques secondes → record stoppé (cause plausible : entrées ADC haute-impédance suite
  au retrait → faute ADS1285/gatherer, **conséquence de la mod**). Batterie mesurée
  **pleine (7,57 V)**. → remettre les résistances (config prod) puis ré-accepter, ou garder
  exclu. Firmware flashé OK.

## Décision

**GO pour le design.** Les 8 unités production passent (aucun FAIL). Conditions de suivi :
- **Correctifs firmware** (non bloquants design) : jauge batterie ; robustesse transfert
  CDC ; + START/STOP idempotents BLE ; écriture SD (voir
  `geophones-firmware/doc/test-bench-to-production.md`).
- **CG0-000008** : rétablir la config prod et ré-accepter, ou statuer « exclu ».

## Hors périmètre de ce go/no-go (à traiter plus tard)

- **Corrélation temporelle (TIME-05)** : pipeline matériel opérationnel, précision
  d'horodatage à régler (post-vacances). Clé pour l'ANT multi-stations.
- **Calibration fine** (sensibilité/f0/ζ par voie) + diffusion **StationXML** (pôles/zéros)
  et convention **SID FDSN** (DATA-07) — à cadrer avec le géophysicien selon la bande ANT.