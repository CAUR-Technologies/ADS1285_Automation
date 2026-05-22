"""
Gestionnaire de configuration INI persistante.

Le fichier config.ini est cree automatiquement avec les valeurs par defaut
au premier lancement, puis modifie par l'interface graphique.

Emplacement :
  - Executable PyInstaller : meme dossier que l'exe
  - Source Python         : racine du projet (dossier parent de config/)
"""

import configparser
import os
import sys

# Racine du projet (fonctionne en mode source ET en mode bundle PyInstaller)
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(_BASE_DIR, "config.ini")

# -----------------------------------------------------------------------
# Valeurs par defaut
# -----------------------------------------------------------------------
_DEFAULTS: dict[str, dict[str, str]] = {
    "ADS1285": {
        "bridge_port":     "9500",
        "sample_rate":     "4000",
        "num_samples":     "1024",
        "register_map":    r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Register Map.xml",
        "python32_path":   r"C:\Python311-32\python.exe",
    },
    "APS": {
        "baud":                       "9600",
        "timeout":                    "2.0",
        "controller_vertical_port":   "COM3",
        "controller_horizontal_port": "COM4",
        "amplifier_vertical_port":    "COM5",
        "amplifier_horizontal_port":  "COM6",
    },
    "Wavetek": {
        "port":    "COM5",
        "baud":    "9600",
        "timeout": "2.0",
    },
    "NI": {
        "device_name":        "Dev1",
        "ai_channels":        "ai0,ai1",
        "sample_rate":        "10000",
        "samples_per_channel": "1000",
    },
    "General": {
        "data_output_dir": "data",
    },
}

_cfg = configparser.ConfigParser()


def load() -> None:
    """Charge config.ini ; cree le fichier avec les defauts si absent."""
    if os.path.exists(CONFIG_FILE):
        _cfg.read(CONFIG_FILE, encoding="utf-8")

    modified = False
    for section, values in _DEFAULTS.items():
        if not _cfg.has_section(section):
            _cfg.add_section(section)
            modified = True
        for key, val in values.items():
            if not _cfg.has_option(section, key):
                _cfg.set(section, key, val)
                modified = True

    if modified:
        save()


def save() -> None:
    """Ecrit config.ini sur disque."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        _cfg.write(fh)


def get(section: str, key: str) -> str:
    return _cfg.get(section, key)


def set_value(section: str, key: str, value: str) -> None:
    if not _cfg.has_section(section):
        _cfg.add_section(section)
    _cfg.set(section, key, str(value))


# Charge au premier import
load()
