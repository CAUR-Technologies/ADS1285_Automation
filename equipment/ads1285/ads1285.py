"""
Module ADS1285 EVM — ADC sismique Texas Instruments
Interface via bridge32 (processus 32-bit) + socket TCP local.

Architecture :
    gui.py / main.py (Python 64-bit  -ou- exe PyInstaller)
        └─ ADS1285  ──socket──►  bridge32.py / bridge32.exe  (32-bit + tiPHIChar.dll)

En mode bundle PyInstaller (sys.frozen=True) le bridge est lance comme
bridge32.exe (place dans le meme dossier que l'executable principal).
En mode source, bridge32.py est lance via ADS1285_PYTHON32_PATH.
"""

import json
import os
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from config.settings import (
    ADS1285_REGISTER_MAP,
    ADS1285_BRIDGE_PORT,
    ADS1285_PYTHON32_PATH,
    ADS1285_SAMPLE_RATE,
    ADS1285_NUM_SAMPLES,
)

# Racine du projet : fonctionne en mode source ET en mode bundle
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BRIDGE_SCRIPT   = os.path.join(_PROJECT_ROOT, "bridge", "bridge32.py")
_BRIDGE_EXE      = os.path.join(_PROJECT_ROOT, "bridge32.exe")
_PHI_BINARIES    = os.path.join(_PROJECT_ROOT, "bridge", "phi_binaries")
_FPGA_BIN        = os.path.join(_PHI_BINARIES, "fpga_189956B.bin")
_PSM_BINS        = sorted(
    [os.path.join(_PHI_BINARIES, f) for f in os.listdir(_PHI_BINARIES)
     if f.startswith("psm_") and f.endswith(".bin")]
) if os.path.isdir(_PHI_BINARIES) else []
_CALL_LOG_JSON   = os.path.join(_PHI_BINARIES, "call_log.json")


class ADS1285:
    """Contrôle l'ADS1285 EVM via le bridge 32-bit."""

    def __init__(self,
                 port: int = ADS1285_BRIDGE_PORT,
                 sample_rate: int = ADS1285_SAMPLE_RATE,
                 num_samples: int = ADS1285_NUM_SAMPLES):
        self._port = port
        self._sample_rate = sample_rate
        self._num_samples = num_samples
        self._sock: socket.socket | None = None
        self._proc: subprocess.Popen | None = None
        self._register_map: dict = {}
        self._req_id = 0

    # ------------------------------------------------------------------
    # Connexion / déconnexion
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Démarre le bridge 32-bit, initialise l'EVM (FPGA + PSM) et ouvre la connexion."""
        self._register_map = _load_register_map(ADS1285_REGISTER_MAP)
        self._start_bridge()
        self._open_socket()

        # Verifier que tous les fichiers necessaires sont presents
        missing = []
        if not os.path.isfile(_FPGA_BIN):      missing.append("fpga binary")
        if not _PSM_BINS:                      missing.append("psm binaries")
        if not os.path.isfile(_CALL_LOG_JSON): missing.append("call_log.json")
        if missing:
            raise RuntimeError(f"Fichiers d'init manquants : {', '.join(missing)}")

        # On envoie uniquement les chemins — bridge32 lit les fichiers lui-meme
        # timeout=120s : PHILoadFPGA + Close + ReInit peut prendre ~30s au total
        print("ADS1285: initialisation complete (FPGA + PSM)...")
        self._call("initialize_full", [
            os.path.abspath(_FPGA_BIN),
            [os.path.abspath(p) for p in _PSM_BINS],
            os.path.abspath(ADS1285_REGISTER_MAP),
            os.path.abspath(_CALL_LOG_JSON),
        ], timeout=120.0)
        # Remettre un timeout raisonnable apres init (qui l'avait pousse a 120s)
        self._sock.settimeout(30.0)

        print("ADS1285 connecté.")

    def disconnect(self) -> None:
        """Ferme la connexion et arrête le bridge."""
        try:
            if self._sock:
                self._sock.settimeout(5.0)
                self._call("close")
                self._call("shutdown")
        except Exception:
            pass
        finally:
            if self._sock:
                self._sock.close()
                self._sock = None
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None
        print("ADS1285 déconnecté.")

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def write_register(self, reg_name: str, value: int) -> int:
        """Écrit une valeur dans un registre ADS1285 par son nom."""
        address = self._resolve(reg_name)
        ret = self._call("write_register", [address, value])
        print(f"[ADS1285] write '{reg_name}' (0x{address:02X}) = 0x{value:02X}  → ret={ret}")
        return ret

    def read_register(self, reg_name: str) -> int:
        """Lit la valeur d'un registre ADS1285 par son nom."""
        address = self._resolve(reg_name)
        resp = self._call("read_register", [address])
        print(f"[ADS1285] read  '{reg_name}' (0x{address:02X}) = 0x{resp['value']:02X}  → ret={resp['ret']}")
        return resp["value"]

    def acquire(self,
                num_samples: int | None = None,
                sample_rate: int | None = None) -> list[int]:
        """
        Acquiert des échantillons 32-bit depuis l'ADS1285.

        Args:
            num_samples: Nombre d'échantillons (puissance de 2 : 256, 512, 1024, ...).
                         Par défaut : valeur de ADS1285_NUM_SAMPLES dans settings.py.
            sample_rate: Taux d'échantillonnage en Hz (4000, 2000, 1000, 500, 250).
                         Par défaut : valeur de ADS1285_SAMPLE_RATE dans settings.py.

        Returns:
            Liste d'entiers 32-bit signés.
        """
        if num_samples is None:
            num_samples = self._num_samples
        if sample_rate is None:
            sample_rate = self._sample_rate

        psm_acq = os.path.join(_PHI_BINARIES, "psm_04_40B.bin")
        psm_seq = os.path.join(_PHI_BINARIES, "psm_05_200B.bin")

        acq_timeout = num_samples / sample_rate + 10.0
        resp = self._call("acquire_samples", [
            num_samples,
            os.path.abspath(psm_acq),
            os.path.abspath(psm_seq),
            sample_rate,
        ], timeout=acq_timeout)
        import struct
        raw: list[int] = resp["data"]

        # Convertir les octets bruts en entiers 32-bit signés little-endian.
        # Le PSM/FPGA écrit en little-endian (natif x86/OpalKelly) — confirmé
        # par la cohérence avec l'interprétation little-endian de reg 4108 dans
        # acquire_samples. PHI_ReadARM_ADC_Data assemble en big-endian côté DLL,
        # mais le flux PSM sort en little-endian.
        raw_bytes = bytes(raw)
        n = len(raw_bytes) // 4
        samples = list(struct.unpack_from(f"<{n}i", raw_bytes))

        return samples[:num_samples]

    def acquire_arm(self,
                    num_samples: int | None = None,
                    sample_rate: int | None = None,
                    selector: int = 0) -> list[int]:
        """
        Acquisition par boucle de lectures single-shot PHI_ReadARM_ADC_Data.

        Alternative à acquire() sans PSM : plus lente (latence socket) mais
        garantit qu'on lit le canal ADC actif. Utile pour diagnostiquer si
        l'acquisition PSM est correcte. Le taux effectif est approché.

        Args:
            num_samples: Nombre d'échantillons. Défaut : ADS1285_NUM_SAMPLES.
            sample_rate: Taux en Hz. Défaut : ADS1285_SAMPLE_RATE.
            selector:    Sélecteur canal (0..3).

        Returns:
            Liste d'entiers 32-bit signés.
        """
        if num_samples is None:
            num_samples = self._num_samples
        if sample_rate is None:
            sample_rate = self._sample_rate

        delay_us = int(1_000_000 / sample_rate)
        # timeout = durée totale + 5s marge
        acq_timeout = num_samples / sample_rate + 5.0
        resp = self._call("acquire_arm", [num_samples, selector, delay_us],
                          timeout=acq_timeout)
        return resp["data"]

    def read_raw_adc(self, selector: int = 0) -> int:
        """
        Lecture single-shot rapide via PHI_ReadARM_ADC_Data (sans PSM).
        Utile pour vérifier la santé de la carte après connexion.

        Args:
            selector: 0..3 — sélecteur de canal ADC.

        Returns:
            Valeur entière 32-bit signée (≈ 1868 quand l'entrée est à la masse).
        """
        resp = self._call("read_arm_adc_data", [selector])
        return resp["value"]

    def check_devices(self) -> int:
        """Retourne le nombre d'EVM détectés."""
        return self._call("check_devices")

    def get_serial_numbers(self) -> str:
        """Retourne les numéros de série des EVM connectés."""
        return self._call("get_serial_numbers")

    def get_version(self) -> str:
        """Retourne la version du firmware PHI."""
        return self._call("get_version")

    def board_reset(self) -> int:
        """Reset la carte EVM."""
        return self._call("board_reset")

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _start_bridge(self) -> None:
        import threading

        if getattr(sys, "frozen", False):
            # Mode bundle : bridge32.exe est dans le meme dossier que l'exe principal
            cmd = [os.path.abspath(_BRIDGE_EXE), "--port", str(self._port)]
        else:
            cmd = [ADS1285_PYTHON32_PATH, os.path.abspath(_BRIDGE_SCRIPT),
                   "--port", str(self._port)]

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # readline() est bloquant — on le met dans un thread pour pouvoir
        # appliquer un timeout sans deadlock.
        # Un thread daemon draine en continu stdout du bridge pour eviter
        # que le pipe soit plein (cause OSError dans le bridge).
        ready = threading.Event()
        first_line = [None]

        def _reader():
            line = self._proc.stdout.readline().decode(errors="replace").strip()
            first_line[0] = line
            ready.set()
            # Drainer le reste de stdout en continu (evite le blocage du pipe)
            for _ in self._proc.stdout:
                pass

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        if not ready.wait(timeout=15.0):
            self._proc.terminate()
            raise RuntimeError("Bridge 32-bit n'a pas répondu dans les 15 secondes.")

        line = first_line[0]
        if self._proc.poll() is not None:
            raise RuntimeError(f"Bridge 32-bit a quitté prématurément. Sortie : {line}")

        # bridge32.py imprime "Ecoute sur localhost:PORT"
        if "localhost" not in line:
            raise RuntimeError(f"Bridge 32-bit: message inattendu : {line!r}")

        print(f"[ADS1285] Bridge démarré : {line}")

    def _open_socket(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect(("127.0.0.1", self._port))
        self._sock.settimeout(10.0)
        self._buf = b""

    def _call(self, cmd: str, args: list | None = None, kwargs: dict | None = None,
              timeout: float | None = None):
        """Envoie une commande JSON au bridge et retourne le résultat."""
        if timeout is not None:
            self._sock.settimeout(timeout)
        self._req_id += 1
        req = {"id": self._req_id, "cmd": cmd, "args": args or [], "kwargs": kwargs or {}}
        self._sock.sendall((json.dumps(req) + "\n").encode())

        # Lire la réponse ligne par ligne
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("Bridge fermé inopinément.")
            self._buf += chunk

        line, self._buf = self._buf.split(b"\n", 1)
        resp = json.loads(line.decode())
        if resp.get("error"):
            raise RuntimeError(f"[bridge32] {resp['error']}")
        return resp["result"]

    def _resolve(self, reg_name: str) -> int:
        addr = self._register_map.get(reg_name)
        if addr is None:
            raise ValueError(f"Registre inconnu : '{reg_name}'. "
                             f"Disponibles : {list(self._register_map.keys())}")
        return addr

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


# ---------------------------------------------------------------------------
# Utilitaire
# ---------------------------------------------------------------------------

def _load_register_map(xml_path: str) -> dict:
    """Parse le Register Map XML TI et retourne {nom: adresse}."""
    register_map = {}
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for reg in root.iter("Register"):
        name    = reg.get("name")    or reg.findtext("Name", "")
        addr_str = reg.get("address") or reg.findtext("Address", "")
        block = reg.find("..")  # bloc parent (ADC ou DAC)
        block_name = ""
        if block is not None:
            block_name = block.findtext("Block_Name", "")
        key = f"{block_name}/{name}" if block_name else name
        if name and addr_str:
            register_map[name] = int(addr_str, 0)        # accès par nom court
            register_map[key]  = int(addr_str, 0)        # accès qualifié
    return register_map
