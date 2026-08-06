"""
Client USB (CDC-ACM) des unités géophone 3 axes, pour le banc de calibration.

Les unités 3 axes (firmware CAUR, branche usb-cdc-interface) exposent un device
USB composite MSD + CDC-ACM (VID 0483 / PID 2545) piloté par un PROTOCOLE TEXTE
LIGNE. Le banc s'en sert pour, autour d'une excitation shaker :
  * configurer l'unité      : CONFIG SET k=v ...
  * lancer/arrêter l'acquis.: START / STOP / SYNC
  * lister/récupérer les .dat: LS / GET (chunks base64)
puis corréler les 3 voies enregistrées avec l'accéléromètre de référence.

Le contrat CDC (commandes, formats) est défini par le firmware `app/bsp/usb_iface`.
Ce module est ADAPTÉ de `GeophoneDevice` de l'outil hôte
`geophones-instrument-console` (copié pour rester autonome ; la source d'origine
n'est PAS modifiée). Ajouts côté banc : helpers START/STOP/SYNC, récupération de
fichiers vers disque, découverte par VID/PID.
"""

import base64
import binascii
import json
import os
import re
import threading
import time

import serial
import serial.tools.list_ports

# Descripteur USB du firmware 3 axes (device composite MSD + CDC-ACM).
GEOPHONE3AXIS_VID = 0x0483
GEOPHONE3AXIS_PID = 0x2545


def discover_units(vid: int = GEOPHONE3AXIS_VID,
                   pid: int = GEOPHONE3AXIS_PID) -> list[tuple[str, str]]:
    """Énumère nativement les unités 3 axes branchées (filtre VID/PID).

    Retourne une liste de (serial_number, port) — `serial.tools.list_ports`
    donne le numéro de série du descripteur USB sans aucune ouverture de port.
    """
    out = []
    for p in serial.tools.list_ports.comports():
        if p.vid == vid and p.pid == pid:
            out.append((p.serial_number or p.device, p.device))
    return out


class Geophone3Axis:
    """Une unité géophone 3 axes : lien série CDC-ACM piloté par le line-protocol."""

    # Clés acceptées par le "CONFIG SET k=v ..." du firmware.
    # geophone_model / geophone_freq_hz ajoutés (firmware develop, PR #146 5bff404) :
    # ils alimentent l'en-tête .dat caurtech.geophone.{model,natural_frequency_hz}.
    CONFIG_KEYS = ("sample_rate_hz", "gain", "survey_id", "samples_by_record",
                   "records_per_file", "max_pitch_deg", "max_roll_deg",
                   "geophone_model", "geophone_freq_hz")

    def __init__(self, port: str, serial_number: str = ""):
        self.port = port
        self.serial_number = serial_number
        self.info: dict = {}   # dernier STATUS?
        self.cfg: dict = {}    # dernier CONFIG?
        self._lock = threading.Lock()
        self._ser: serial.Serial | None = None

    # ---- lien série ----------------------------------------------------
    def _open(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            # Baud sans effet pour l'USB CDC-ACM, mais pyserial l'exige.
            self._ser = serial.Serial(self.port, baudrate=115200, timeout=0.3)
            # Le firmware GATE sa TX CDC-ACM sur DTR (il ne répond pas tant qu'un
            # hôte ne l'a pas asserté). On force DTR/RTS et on laisse un instant
            # au device pour enregistrer la connexion avant la 1re commande.
            self._ser.dtr = True
            self._ser.rts = True
            time.sleep(0.2)
        return self._ser

    def connect(self) -> None:
        with self._lock:
            self._open()

    def close(self) -> None:
        with self._lock:
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.close()
                except OSError:
                    pass
            self._ser = None

    def _exchange(self, cmd: str, terminator: str | None = None,
                  timeout: float = 3.0) -> list[str]:
        """Envoie `cmd` et collecte les lignes de réponse jusqu'à `terminator`
        (ou une ligne). Découpe sur CR/LF (framing \\n vs \\r\\n indifférent)."""
        with self._lock:
            ser = self._open()
            ser.reset_input_buffer()
            ser.write((cmd + "\n").encode())
            ser.flush()
            buf = bytearray()
            deadline = time.time() + timeout
            while time.time() < deadline:
                chunk = ser.read(ser.in_waiting or 1)
                if not chunk:
                    continue
                buf += chunk
                text = buf.decode(errors="replace")
                if terminator is not None:
                    if terminator in text:
                        break
                elif "\n" in text or "\r" in text:
                    break
            return [ln.strip()
                    for ln in re.split(r"[\r\n]+", buf.decode(errors="replace"))
                    if ln.strip()]

    # ---- interrogation -------------------------------------------------
    def status(self) -> dict:
        self.info = self._parse_json(self._exchange("STATUS?"))
        return self.info

    def config(self) -> dict:
        self.cfg = self._parse_json(self._exchange("CONFIG?"))
        return self.cfg

    # ---- configuration / contrôle acquisition --------------------------
    def set_config(self, fields: dict) -> list[str]:
        """Applique seulement les champs fournis via un unique CONFIG SET."""
        pairs = [f"{k}={fields[k]}" for k in self.CONFIG_KEYS
                 if fields.get(k) not in (None, "")]
        if not pairs:
            return ["ERR no fields"]
        return self._exchange("CONFIG SET " + " ".join(pairs))

    def start(self) -> list[str]:
        """Démarre l'acquisition sur l'unité (enregistrement SD)."""
        return self._exchange("START")

    def stop(self) -> list[str]:
        """Arrête l'acquisition sur l'unité."""
        return self._exchange("STOP")

    def sync(self) -> list[str]:
        """Marqueur/synchronisation temporelle (SYNC) — pour l'alignement GNSS."""
        return self._exchange("SYNC")

    def command(self, cmd: str) -> list[str]:
        """Commande libre (CONFIG SET k=v ..., SYNC, ...)."""
        return self._exchange(cmd)

    # ---- fichiers ------------------------------------------------------
    def ls(self, path: str = "") -> list[dict]:
        """Liste les enregistrements (F,<path>,<size> / D,<dir>)."""
        cmd = "LS" if not path else f"LS {path}"
        files: list[dict] = []
        for ln in self._exchange(cmd, terminator="LS DONE", timeout=8.0):
            if ln.startswith("F,"):
                parts = ln.split(",")
                files.append({
                    "path": parts[1],
                    "size": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                })
            elif ln.startswith("D,"):
                files.append({"path": ln[2:], "dir": True})
        return files

    def get_file(self, path: str) -> bytes:
        """Récupère un enregistrement via CDC (GET → chunks base64) en octets bruts."""
        data = bytearray()
        for ln in self._exchange(f"GET {path}", terminator="GET DONE", timeout=120.0):
            if ln.startswith("D,"):
                try:
                    data += base64.b64decode(ln[2:])
                except (ValueError, binascii.Error):
                    pass
        return bytes(data)

    def pull_all(self, dest_dir: str, path: str = "") -> list[str]:
        """Récupère TOUS les fichiers (LS puis GET) vers `dest_dir`.

        Retourne la liste des chemins locaux écrits. Le nom local est préfixé du
        numéro de série de l'unité pour éviter les collisions entre unités.
        """
        os.makedirs(dest_dir, exist_ok=True)
        written = []
        for entry in self.ls(path):
            if entry.get("dir"):
                continue
            remote = entry["path"]
            data = self.get_file(remote)
            base = remote.replace("/", "_").lstrip("_")
            prefix = f"{self.serial_number}_" if self.serial_number else ""
            local = os.path.join(dest_dir, prefix + base)
            with open(local, "wb") as fh:
                fh.write(data)
            written.append(local)
        return written

    @staticmethod
    def _parse_json(lines: list[str]) -> dict:
        for ln in lines:
            try:
                return json.loads(ln)
            except json.JSONDecodeError:
                continue
        return {"raw": lines}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
