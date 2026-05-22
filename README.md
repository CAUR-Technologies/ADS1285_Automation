# ADS1285 Automation

Système d'automatisation pour l'**ADS1285 EVM** — mesure et caractérisation de géophones avec acquisition synchronisée et balayage fréquentiel.

## 🎯 Vue d'ensemble

Ce projet automatise la mesure des réponses sismiques d'équipements via :
- **ADC ADS1285 EVM** (Texas Instruments) — acquisition haute résolution 24-bit
- **Générateur Wavetek 39A** — balayage fréquentiel contrôlé
- **Table de vibration APS** (Spektra) — stimulus mécanique avec retour d'accéléromètres
- **Accéléromètres NI USB-6221** — mesure de la réponse

### Séquence type
1. Connexion à tous les équipements
2. Configuration initiale (fréquence, amplitude, gain)
3. Balayage fréquentiel synchronisé
4. Acquisition simultanée ADC + accéléromètres
5. Sauvegarde des données (format NumPy `.npz`)
6. Visualisation amplitude vs fréquence

## 📦 Architecture

```
ADS1285_Automation/
├── equipment/              # Pilotes des équipements
│   ├── ads1285/           # ADC ADS1285 (bridge 32-bit)
│   ├── wavetek/           # Générateur Wavetek 39A
│   ├── aps/               # Contrôleur APS 0109 (Spektra)
│   └── accelerometer/     # Accéléromètres NI-DAQmx
├── config/                # Gestion de configuration
├── bridge/                # Bridge 32-bit (DLL Texas Instruments)
├── main.py               # Point d'entrée (balayage simple)
├── gui.py                # Interface graphique (Tkinter)
└── tests/                # Tests unitaires
```

## 🚀 Installation

### Prérequis
- **Python 3.10+** (64-bit)
- **Python 3.11 32-bit** (pour bridge ADS1285)
- **Texas Instruments PHI Package** (DLL + binaires FPGA/PSM)
- **NI-DAQmx** (pour accéléromètres)
- **Pilotes série USB** (CH340, FTDI, etc.)

### Setup

```bash
# Cloner le repo
git clone https://github.com/CAUR-Technologies/ADS1285_Automation.git
cd ADS1285_Automation

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

Interface graphique (Tkinter) avec :
- Connexion individuelle de chaque équipement
- Configuration interactive (fréquence, gain, amplitude)
- Acquisition simple ou balayage
- Visualisation temps-réel et FFT

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
baud = 9600
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
| ADC | Texas Instruments ADS1285 EVM | TCP/IP (bridge 32-bit) | `ADS1285` |
| Générateur | Wavetek Model 39A | RS-232 SCPI-like | `Wavetek39A` |
| Contrôleur | APS 0109 (Spektra) | RS-232 SCPI | `APSController` |
| Accéléromètres | NI USB-6221 | NI-DAQmx | `Accelerometer` |

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

Les résultats sont sauvegardés en `.npz` (NumPy compressed) dans `data/` :

```python
import numpy as np

# Charger les résultats
data = np.load("data/sweep_20260522_143022.npz")

# Clés disponibles
for key in data.files:
    print(f"{key}: {data[key].shape}")
# Exemple :
# f1.0Hz_adc: (4096,)
# f1.0Hz_accel: (2, 1000)
```

## ⚠️ Notes de sécurité

- **APS 0109** : Les commandes sans argument (STA, STP, RST) ne retournent rien
- **ADS1285 Bridge** : Processus 32-bit séparé, TCP sur `localhost:9500`
- **Timeout** : Les accéléromètres NI-DAQmx peuvent bloquer si pas de données

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

Voir les fichiers `CLAUDE.md` dans chaque sous-dossier `equipment/` :
- [`equipment/ads1285/CLAUDE.md`](equipment/ads1285/CLAUDE.md) — Protocole bridge ADS1285
- [`equipment/aps/CLAUDE.md`](equipment/aps/CLAUDE.md) — Protocole RS-232 APS 0109
- [`equipment/wavetek/CLAUDE.md`](equipment/wavetek/CLAUDE.md) — Protocole SCPI Wavetek 39A

## 📝 Licence

À définir (ajuster selon votre organisation)

## 👥 Auteurs

- **Développement initial** : Claude Code (Anthropic)
- **Organisation** : CAUR-Technologies

## 📞 Support

Pour les bugs ou questions : GitHub Issues

---

**Dernière mise à jour** : Mai 2026
