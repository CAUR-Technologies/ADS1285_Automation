# Geophones Characterization Testbench

Système d'automatisation pour l'**ADS1285 EVM** — mesure et caractérisation de géophones avec acquisition synchronisée et balayage fréquentiel.

## 🎯 Vue d'ensemble

Ce projet automatise l'**étalonnage de géophones** pour l'Ambient Noise
Tomography (ANT), via :
- **ADC ADS1285 EVM** (Texas Instruments) — numérise le géophone testé (bridge 32-bit)
- **Générateur Wavetek 39A** — source du signal d'excitation
- **Table de vibration APS** — 2 axes (V/H), chacun : shaker APS 113 + contrôleur
  APS 0109 + ampli APS 125 ; Wavetek réparti aux deux chaînes par un **splitter**
- **Accéléromètre de référence** Silicon Designs 2240-005 → NI USB-6221
  (un par axe, canaux NI distincts)

> 📖 **Opérateurs** : voir le mode d'emploi pas-à-pas
> [`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md).

### Méthode (étalonnage en deux étapes)
1. **Fonction de transfert du banc** `H_banc(f) = a_table(f) / V_wavetek(f)` [g/V]
   — caractérise le shaker+ampli, mesurée avec l'accéléromètre de référence.
2. **Sensibilité du géophone** `H_géo(f) = V_géo(f) / a_table(f)` [counts/g].

À chaque fréquence, le logiciel : plafonne l'amplitude (intersection des limites
**déplacement / vitesse / accélération** — la limite de vitesse, calculée par
géophone, borne sa sortie pour éviter la saturation et donne un **balayage à
vitesse constante**) → adapte la stiffness du contrôleur → asservit l'amplitude en
boucle fermée sur l'accéléromètre → acquiert le géophone → arrête tout sur
overtravel. Le transfert banc (sans géophone monté) excite à pleine amplitude.
Voir [`docs/CALIBRATION_PROTOCOL.md`](docs/CALIBRATION_PROTOCOL.md).

## 📦 Architecture

```
geophones-characterization-testbench/
├── constants.py            # Constantes physiques/matérielles immuables
├── equipment/              # Pilotes + orchestration
│   ├── ads1285/           # ADC ADS1285 (bridge 32-bit) — géophone testé
│   ├── wavetek/           # Générateur Wavetek 39A
│   ├── aps/               # Contrôleur APS 0109 + shaker_physics.py
│   ├── accelerometer/     # Accéléromètre de référence (NI-DAQmx)
│   ├── dsp.py             # Détection cohérente (lock-in), SNR, THD
│   └── testbench.py       # Orchestrateur TestBench (étalonnage)
├── config/                # config.ini + settings.py
├── bridge/                # Bridge 32-bit (DLL Texas Instruments)
├── docs/                  # Guide utilisateur + protocole de calibration
├── gui.py                # Interface graphique (Tkinter)
└── tests/                # Tests unitaires (physique, DSP)
```

## 🚀 Installation

### Prérequis
- **Python 3.11** (64-bit) — version épinglée du projet, **pas 3.12**
- **Python 3.11 32-bit** (`C:\Python311-32`) — requis pour le bridge ADS1285
- **Texas Instruments PHI Package** (DLL + binaires FPGA/PSM)
- **NI-DAQmx** (pour accéléromètres)
- **Pilotes série USB** (CH340, FTDI, etc.)

> ⚠️ **Version Python** : le projet est figé sur **3.11** (64-bit ET 32-bit). Une
> autre version (ex. 3.12) peut coexister sur la machine, mais **n'utilisez pas
> 3.12 ici** : le bridge ADS1285 a besoin d'un interpréteur **32-bit**, et seul
> `C:\Python311-32` (3.11) est disponible (il n'existe pas de 3.12 32-bit). Créez
> le venv 64-bit avec Python 3.11 (`py -3.11 -m venv venv`).

### Setup

```bash
# Cloner le repo
git clone https://github.com/CAUR-Technologies/geophones-characterization-testbench.git
cd geophones-characterization-testbench

# Créer venv Python 64-bit
python -m venv venv
venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les ports COM dans config.ini
notepad config.ini
```

## 🎮 Utilisation

### Mode ligne de commande

```python
python main.py
```

Exécute un balayage fréquentiel sur 7 fréquences (1-100 Hz) avec sauvegarde `.npz`.

### Mode GUI

```python
python gui.py
```

Interface graphique (Tkinter) — voir [`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md) :
- Connexion individuelle de chaque équipement (+ sélection axe V/H — **Horizontal
  par défaut**, gain APS 125)
- Sélection du géophone testé (fixe aussi le plafond de vitesse anti-saturation),
  centrage ZER, plancher de bruit
- **Transfert banc (H_banc)**, **balayage**, **linéarité**, **transversale**,
  **campagne 2 axes** et **vérification quotidienne**
- Visualisation temps-réel, FFT, sensibilité (counts/g, vitesse ou normalisé +
  ajustement `G0/f0/ζ`), H_banc, et onglet **Comparaison** (superposition de
  balayages sauvegardés)
- **Sauvegarde automatique** horodatée par cas (CSV + NPZ dans `data/`), traçable
  (géophone, axe, gains, plancher de bruit, ajustement, formes d'onde)

### Utilisation programmatique

```python
from equipment.ads1285 import ADS1285
from equipment.wavetek import Wavetek39A
from equipment.aps import APSController

with (
    ADS1285() as adc,
    Wavetek39A() as gen,
    APSController("vertical") as aps_v,
):
    gen.configure_frequency_sweep([1, 10, 100])
    gen.enable_output()
    
    for freq in [1, 10, 100]:
        gen.set_frequency(freq)
        samples = adc.acquire(num_samples=4096)
        print(f"Freq={freq} Hz: {len(samples)} samples acquis")
```

## ⚙️ Configuration

Le fichier `config.ini` contient :

```ini
[ADS1285]
bridge_port = 9500
sample_rate = 4000
num_samples = 1024

[APS]
baud = 19200
controller_vertical_port = COM3
controller_horizontal_port = COM4

[Wavetek]
port = COM5
baud = 9600

[NI]
device_name = Dev1
ai_channels = ai0,ai1
sample_rate = 10000
```

Adapter les **ports COM** selon votre matériel.

## 📋 Équipements supportés

| Équipement | Modèle | Interface | Classe |
|-----------|--------|-----------|--------|
| ADC (géophone) | Texas Instruments ADS1285 EVM | TCP/IP (bridge 32-bit) | `ADS1285` |
| Générateur | Wavetek Model 39A | RS-232 (SCPI-like, CRLF) | `Wavetek39A` |
| Contrôleur | APS 0109 (Spektra) | RS-232 custom, 19200, terminaison `\x00` | `APSController` |
| Amplificateur | APS 125 (×2, V+H) | **manuel** — knobs Gain (dB) + Current Limit (A RMS) saisis/tracés | — |
| Shaker | APS 113 (×2, ±38 mm, 133 N) | via APS 0109 | `shaker_physics` |
| Accéléromètre réf. | Silicon Designs 2240-005 (×2, un/axe) → NI USB-6221 | NI-DAQmx | `Accelerometer` |

## 🔧 Développement

### Structure des modules equipment

Chaque équipement est un sous-package avec :
- `__init__.py` — réexporte la classe principale
- `{nom}.py` — implémentation
- `CLAUDE.md` — spécifications du protocole

Exemple : `equipment/ads1285/`
- `ads1285.py` — classe ADS1285 + interface socket
- `CLAUDE.md` — doc protocole bridge

### Tests

```bash
python -m pytest tests/
```

## 📊 Format de sortie

**Sauvegarde automatique** : chaque acquisition et calibration écrit ses fichiers
dans `data/`, nommés par cas et horodatés `<cas>[_<géophone>][_<axe>]_<date>_<heure>` :
`acquisition_*`, `balayage_*`, `transfert_banc_*`, `linearite_*`,
`verif_quotidienne_*`, `transversale_*`, `plancher_bruit_*` (CSV + NPZ selon le cas).
Le bouton **Sauvegarder** reste disponible pour un export manuel.

**CSV (balayage)** : en-tête de métadonnées (`# geophone`, `# date`, `# axis`,
`# aps125_gain_*`, `# noise_floor_*`, ajustement `# fit_G0_counts_per_mps / fit_f0_hz
/ fit_zeta / fit_rms_error_db`) ; puis une ligne par point :
`axis, aps125_gain, aps125_current_limit, freq_hz, target_g, measured_g, vpp,
stiffness, displacement_mm, peak_velocity_mps, safety_margin_mm, snr_db, thd_percent,
geophone_counts_peak, sensitivity_counts_per_g, skipped, note, sensitivity_counts_per_mps`.

Le **balayage** s'écrit **incrémentalement** (rien n'est perdu si la séquence
s'interrompt) : la table CSV est complétée à chaque point, et chaque point écrit ses
**formes d'onde brutes dans un fichier séparé** `onde_<géo>_<axe>_<freq>Hz_<ts>.npz`.
En fin de séquence : l'ajustement `(G0, f0, ζ)` est ajouté au CSV et un NPZ résumé
est écrit.

**NPZ résumé (balayage)** — pour l'onglet Comparaison, sans formes d'onde :
```python
import numpy as np
data = np.load("data/balayage_HG-5VHS_horizontal_2026-05-28_14-25-59.npz")
# Métadonnées : geophone_model, date, aps125_*, noise_floor_*
# Résumé      : freq_hz, summary_sensitivity_counts_per_g, *_counts_per_mps, *_normalized
# Ajustement  : fit_G0_counts_per_mps, fit_f0_hz, fit_zeta, fit_rms_error_db

# Formes d'onde par point (données temporelles) :
onde = np.load("data/onde_HG-5VHS_horizontal_10Hz_2026-05-28_14-25-59.npz")
# geo_wave (+geo_rate), accel_wave (+accel_fs), freq_hz, sensitivity_counts_per_g, ...
```

## ⚠️ Notes de sécurité

- **Ne jamais modifier les knobs de l'APS 125 pendant un étalonnage** (ampli
  manuel → invisible au logiciel ; la valeur est saisie et tracée).
- **Centrage ZER avant tout signal** ; le logiciel plafonne l'amplitude dans la
  course (±38 mm) et **coupe l'excitation sur overtravel**.
- **ADS1285 Bridge** : processus 32-bit séparé, TCP sur `localhost:9500`.
- **Timeout** : les accéléromètres NI-DAQmx peuvent bloquer si pas de données.

Détail complet : [`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md) §3.

## 🐛 Troubleshooting

### "Port COM fermé"
→ Vérifier `config.ini` et les câbles USB

### "Bridge 32-bit ne répond pas"
→ Vérifier que `bridge/fpga_189956B.bin` et PSM binaires existent

### "Module nidaqmx non trouvé"
→ `pip install nidaqmx` et installer NI-DAQmx Runtime

### "Pylance: serial could not be resolved"
→ VS Code → Command Palette → "Python: Select Interpreter" → venv

## 📚 Documentation détaillée

**Opérateur :**
- [`docs/GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md) — mode d'emploi pas-à-pas
- [`docs/CALIBRATION_PROTOCOL.md`](docs/CALIBRATION_PROTOCOL.md) — protocole métrologique

**Développeur / protocoles instruments :**
- [`CLAUDE.md`](CLAUDE.md) — vue d'ensemble + règles + architecture
- [`equipment/CLAUDE.md`](equipment/CLAUDE.md) — physique du banc
- [`equipment/ads1285/CLAUDE.md`](equipment/ads1285/CLAUDE.md) — bridge ADS1285
- [`equipment/aps/CLAUDE.md`](equipment/aps/CLAUDE.md) — RS-232 APS 0109 (terminaison `\x00`)
- [`equipment/wavetek/CLAUDE.md`](equipment/wavetek/CLAUDE.md) — Wavetek 39A

## 📝 Licence

À définir (ajuster selon votre organisation)

## 👥 Auteurs

- **Développement initial** : Claude Code (Anthropic)
- **Organisation** : CAUR-Technologies

## 📞 Support

Pour les bugs ou questions : GitHub Issues

---

**Dernière mise à jour** : 28 mai 2026
