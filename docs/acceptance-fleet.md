# Acceptation produit — passage des 9 prototypes (go/no-go design)

Procédure pour valider les 9 unités avant vendredi. **USB seul, pas de shaker.**
Le banc d'acceptation `tools/acceptance.py` teste, par unité (~2 min), les points de
la matrice V1–V15 atteignables via l'interface CDC — les **usages produit RÉELS**
(config + transfert de données), sans provoquer le gel du board.

## Rappels de contexte (findings de la campagne)

- **USB = config + transfert seulement** (jamais actif pendant l'enregistrement en
  champ). Le **transfert de données est FIABLE** (testé : 39/39 puis 186/186, ~0–2 %
  de fichiers avec un record corrompu, récupérés par le lecteur tolérant).
- Le **START/STOP d'enregistrement par USB gèle le board par intermittence** — c'est
  **test-only** (en champ le record démarre au **bouton/BLE**). Le harnais par défaut
  **ne fait donc PAS de START-USB** → il ne gèle pas le board.
- `battery` du firmware lit parfois `1` (bug intermittent) → V11 = WARN si suspect.

## Prérequis (une fois)

1. Fermer le GUI 3 axes s'il tourne (libère le port USB de l'unité).
2. Utiliser le **python du venv** (dépendances nidaqmx/pyserial/simplemseed).

## Par unité (répéter × 9)

1. Brancher l'unité en USB. Vérifier qu'elle a **au moins un survey sur sa SD**
   (données d'un run précédent). Sinon : **enregistrer ~30 s au BOUTON** (record
   réel, pas USB), puis stop au bouton — ça donne un V2/V7 propre.
2. Lancer :
   ```
   .\venv\Scripts\python.exe tools\acceptance.py
   ```
3. Lire le verdict `>>> <serial> : PASS/WARN/FAIL <<<`. Résultat écrit dans
   `data/acceptance/<serial>.json`.
4. Si le board **gèle** (rare en mode défaut) : reset-le et relance. Les `.dat`
   survivent sur la SD.

## Agréger la flotte

```
.\venv\Scripts\python.exe tools\acceptance.py --fleet
```
→ matrice unités × tests : `.`=PASS `!`=WARN `X`=FAIL `-`=N/A, + compte PASS/WARN/FAIL.

## Interprétation des verdicts

| Test | PASS | WARN (acceptable) | FAIL (à investiguer) |
|---|---|---|---|
| **V1 boot** | uptime monotone | — | reboot en boucle / muet |
| **V13 identité/rev** | serial+fw+hwrev lus | — | champ manquant |
| **V6 IMU** | \|g\|≈1 | \|g\| hors [0,8;1,2] | aucune trame IMU |
| **CFG** | aller-retour OK | — | échec écriture/relecture |
| **V11 batterie** | valeur plausible | lit `1` (bug FW connu) | non numérique |
| **V7 transfert** | 0 corruption | < 10 % corrompus | FREEZE / ≥ 10 % |
| **V2 ADC ×3** | 3 voies vivantes | **SATURÉ** (ampli d'enreg., pas un défaut) | voie **manquante** ou **figée** |
| **V8 miniSEED** | fichiers parsés | — | illisibles |
| **V4/V15 E2E** | — | — | `N/A` = record frais à valider au bouton |

**Go/no-go design** : une unité **PASS ou WARN** sur V1/V13/V6/CFG/V11/V7/V2/V8 est
**bonne** (boot, identité, IMU, config, transfert fiable, 3 ADC présents). Un **FAIL**
sur V2 (voie manquante/figée), V7 (freeze/≥10 % corruption) ou V8 = **défaut à lever**.

## À vérifier MANUELLEMENT (non automatisable via CDC)

Cocher par unité :

- [ ] **V9 USB-MSD** : brancher l'USB, le disque de masse monte (fichiers visibles).
- [ ] **V10 LEDs** : les 4 LEDs répondent aux états attendus (boot, fix GPS, record).
- [ ] **V15 record réel** : **appuyer sur le bouton** → l'unité enregistre (LED) →
      stop bouton → relancer `acceptance.py` : le nouveau survey doit donner V2/V7 PASS.
- [ ] **V3 synchro inter-voies** / **V5 dérive horloge** : nécessitent le banc
      shaker+GNSS (corrélation temporelle `time_correlation.py`, à roder — reporté).
- [ ] **V14 watchdog** : provoquer un blocage → reset auto ; horloge tient au reboot.
- [ ] **V12 BLE** : N/A sur V2/V3.0 (contrôleur BlueNRG sur V3.1).

## Limites connues

- **V2 sur survey existant** : la saturation dépend de l'amplitude du run enregistré
  (une caractérisation à la résonance sature) → WARN, pas un défaut. Pour un V2 net,
  utiliser un **enregistrement ambiant** (bouton, faible amplitude).
- **Corrélation temporelle (TIME-05)** : le pipeline `time_correlation.py` fonctionne
  (shaker+GNSS+1PPS) mais la précision d'alignement des horodatages n'est pas encore
  réglée (étiquetage 1PPS↔NMEA + précision d'horodatage firmware) → **post-vacances**.
