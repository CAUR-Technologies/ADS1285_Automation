"""
Module APS 0109 — Contrôleur de position SPEKTRA
Interface RS-232 via pyserial.

Protocole (confirmé sur matériel, firmware 1.02.01) :
- Baud : 19200, 8 bits, parité aucune, 1 stop
- Terminaison de commande : \\x00 (null byte)
- Réponse terminée par \\x00, au format : "<commande> <valeur> OK"
    ex. "FWV? 1.02.01 OK", "SER? 209 OK", "ZER? 0 OK"
  Les commandes sans valeur de retour répondent "<commande> OK".
  Une erreur contient le token "ERR".
"""

import serial
import time
from config.settings import (
    APS_CONTROLLER_VERTICAL_PORT,
    APS_CONTROLLER_HORIZONTAL_PORT,
    APS_BAUD,
    APS_TIMEOUT,
)
from equipment.instrlog import get_logger


class APSController:
    """Contrôle un contrôleur de position APS 0109 via RS-232."""

    VERTICAL   = "vertical"
    HORIZONTAL = "horizontal"

    _DEFAULT_PORTS = {
        VERTICAL:   APS_CONTROLLER_VERTICAL_PORT,
        HORIZONTAL: APS_CONTROLLER_HORIZONTAL_PORT,
    }

    # Protocole
    _TERMINATOR = b"\x00"
    _OK_SUFFIX = "OK"
    _ERROR_TOKEN = "ERR"

    def __init__(self, axis: str, port: str | None = None, baud: int = APS_BAUD):
        """
        Parameters
        ----------
        axis : "vertical" ou "horizontal"
        port : port COM (défaut : valeur de settings selon l'axe)
        baud : vitesse en bauds (défaut : 19200, valeur matérielle de l'APS 0109)
        """
        if axis not in (self.VERTICAL, self.HORIZONTAL):
            raise ValueError(f"Axe invalide : '{axis}'. Utiliser 'vertical' ou 'horizontal'.")
        self._axis = axis
        self._port = port or self._DEFAULT_PORTS[axis]
        self._baud = baud
        self._serial: serial.Serial | None = None
        self._log = get_logger("APS")

    @property
    def axis(self) -> str:
        return self._axis

    # ─────────────────────────────────────────────────────────────────────
    # Connexion / Déconnexion
    # ─────────────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Établit la connexion série avec l'APS 0109."""
        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=APS_TIMEOUT,
        )
        # Certaines unités (MCU type ATmega) redémarrent à l'ouverture du port
        # (auto-reset DTR) et émettent une bannière 'Mega64…'. On laisse passer
        # le boot puis on vide le buffer pour ne pas la lire sur 1re commande.
        time.sleep(0.5)
        self._drain()
        print(f"APS 0109 [{self._axis}] connecté sur {self._port} (baud={self._baud}).")

    def disconnect(self) -> None:
        """Ferme la connexion série."""
        if self._serial and self._serial.is_open:
            self._serial.close()
        print(f"APS 0109 [{self._axis}] déconnecté.")

    # ─────────────────────────────────────────────────────────────────────
    # Communication bas niveau
    # ─────────────────────────────────────────────────────────────────────

    def _send_raw(self, cmd: str) -> str:
        """Envoie une commande (terminée \\x00) et retourne la réponse brute
        (lue jusqu'au \\x00 ou timeout)."""
        if not self._serial or not self._serial.is_open:
            raise RuntimeError(f"APS 0109 [{self._axis}] non connecté.")
        self._serial.reset_input_buffer()
        self._serial.write((cmd + "\x00").encode("ascii"))
        time.sleep(0.05)
        response = b""
        while True:
            byte = self._serial.read(1)
            if not byte or byte == b"\x00":
                break
            response += byte
        decoded = response.decode("ascii", errors="replace").strip()
        self._log.debug(f"[{self._axis}] TX {cmd!r}  ->  RX {decoded!r}")
        return decoded

    def _drain(self) -> None:
        """Vide toute donnée résiduelle (bannière de boot 'Mega64…' en transit)."""
        if not (self._serial and self._serial.is_open):
            return
        self._serial.reset_input_buffer()
        old = self._serial.timeout
        self._serial.timeout = 0.2
        try:
            while self._serial.read(128):
                pass
        finally:
            self._serial.timeout = old

    def _looks_valid(self, resp: str) -> bool:
        up = resp.upper()
        return (self._OK_SUFFIX in up) or (self._ERROR_TOKEN in up)

    def _transact(self, cmd: str, retries: int = 4) -> str:
        """
        Envoie cmd et lit la réponse, en ignorant une éventuelle bannière de
        démarrage du MCU (ex. 'Mega64 \\r??' après un reset/auto-reset DTR) :
        si la réponse n'est ni OK ni ERR, vide le buffer, laisse le temps au
        boot, et retente.
        """
        resp = ""
        for attempt in range(retries):
            resp = self._send_raw(cmd)
            if self._looks_valid(resp):
                return resp
            self._log.debug(f"[{self._axis}] réponse inattendue {resp!r} "
                            f"(bannière de boot ?) — retry {attempt + 1}/{retries}")
            self._drain()
            time.sleep(0.3)   # laisser l'unité finir son boot avant de retenter
        return resp

    def _send_command(self, cmd: str, expect_ok: bool = True) -> str:
        """Envoie une commande de réglage ; vérifie que la réponse finit par 'OK'."""
        resp = self._transact(cmd)
        if expect_ok:
            up = resp.upper()
            if self._ERROR_TOKEN in up:
                msg = f"Erreur APS 0109 [{self._axis}] ({cmd}) : {resp!r}"
                self._log.error(msg)
                raise RuntimeError(msg)
            if not up.endswith(self._OK_SUFFIX):
                msg = f"Réponse APS 0109 inattendue ({cmd}) : {resp!r}"
                self._log.error(msg)
                raise RuntimeError(msg)
        return resp

    def _query_value(self, cmd: str) -> str:
        """
        Envoie une query et extrait la valeur du format '<commande> <valeur> OK'.
        Ex. : 'ZER? 0 OK' -> '0' ; 'FWV? 1.02.01 OK' -> '1.02.01'.
        """
        resp = self._transact(cmd)
        if self._ERROR_TOKEN in resp.upper():
            msg = f"Erreur APS 0109 [{self._axis}] ({cmd}) : {resp!r}"
            self._log.error(msg)
            raise RuntimeError(msg)
        val = resp.strip()
        if val.upper().startswith(cmd.upper()):       # retirer l'écho
            val = val[len(cmd):].strip()
        if val.upper().endswith(self._OK_SUFFIX):     # retirer le 'OK'
            val = val[:-len(self._OK_SUFFIX)].strip()
        return val

    def _query_int(self, cmd: str) -> int:
        val = self._query_value(cmd)
        try:
            return int(val)
        except ValueError:
            raise RuntimeError(f"Réponse APS 0109 non entière ({cmd}) : {val!r}")

    # ─────────────────────────────────────────────────────────────────────
    # Erreurs
    # ─────────────────────────────────────────────────────────────────────

    def get_last_error(self) -> str:
        """Retourne le dernier message d'erreur (commande GES)."""
        return self._query_value("GES")

    # ─────────────────────────────────────────────────────────────────────
    # Position zéro
    # ─────────────────────────────────────────────────────────────────────

    def set_zero_position(self, value: int) -> None:
        """Définit la position zéro (ZER, -99..99)."""
        if not (-99 <= value <= 99):
            raise ValueError(f"Zéro position doit être entre -99 et 99, reçu: {value}")
        self._send_command(f"ZER {value}")

    def get_zero_position(self) -> int:
        """Retourne la position zéro (ZER?)."""
        return self._query_int("ZER?")

    def set_position(self, position: float) -> None:
        raise NotImplementedError(
            "APS 0109 n'a pas de commande de positionnement direct. "
            "Utiliser start() pour lancer le mouvement contrôlé."
        )

    # ─────────────────────────────────────────────────────────────────────
    # Contrôle du contrôleur
    # ─────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le contrôleur (STA)."""
        self._send_command("STA")

    def get_start_status(self) -> bool:
        """True si le contrôleur est en marche (STA?)."""
        return bool(self._query_int("STA?"))

    def stop(self) -> None:
        """Arrête le contrôleur (STP)."""
        self._send_command("STP")

    def get_stop_status(self) -> str:
        """État d'arrêt (STP?)."""
        return self._query_value("STP?")

    # ─────────────────────────────────────────────────────────────────────
    # Rigidité (stiffness)
    # ─────────────────────────────────────────────────────────────────────

    def set_stiffness(self, value: int) -> None:
        """Définit la rigidité (STF, 0..31)."""
        if not (0 <= value <= 31):
            raise ValueError(f"Rigidité doit être entre 0 et 31, reçu: {value}")
        self._send_command(f"STF {value}")

    def get_stiffness(self) -> int:
        """Retourne la rigidité (STF?)."""
        return self._query_int("STF?")

    def set_stiffness_start_value(self, value: int) -> None:
        """Définit la valeur de démarrage de rigidité (SSS, 0..31)."""
        if not (0 <= value <= 31):
            raise ValueError(f"Rigidité de démarrage doit être entre 0 et 31, reçu: {value}")
        self._send_command(f"SSS {value}")

    def get_stiffness_start_value(self) -> int:
        """Retourne la valeur de démarrage de rigidité (SSS?)."""
        return self._query_int("SSS?")

    # ─────────────────────────────────────────────────────────────────────
    # Limites de position
    # ─────────────────────────────────────────────────────────────────────

    def set_position_max(self, value: int) -> None:
        """Définit la position maximale (PMA, 0..1023)."""
        if not (0 <= value <= 1023):
            raise ValueError(f"Position max doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"PMA {value}")

    def get_position_max(self) -> int:
        """Retourne la position maximale (PMA?)."""
        return self._query_int("PMA?")

    def set_position_min(self, value: int) -> None:
        """Définit la position minimale (PMI, 0..1023)."""
        if not (0 <= value <= 1023):
            raise ValueError(f"Position min doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"PMI {value}")

    def get_position_min(self) -> int:
        """Retourne la position minimale (PMI?)."""
        return self._query_int("PMI?")

    # ─────────────────────────────────────────────────────────────────────
    # Sécurité / mouvement
    # ─────────────────────────────────────────────────────────────────────

    def set_overtravel_tolerance(self, value: int) -> None:
        """Définit la tolérance de surcourse (OTT, 0..1023)."""
        if not (0 <= value <= 1023):
            raise ValueError(f"Tolérance doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"OTT {value}")

    def get_overtravel_tolerance(self) -> int:
        """Retourne la tolérance de surcourse (OTT?)."""
        return self._query_int("OTT?")

    def set_wait_time_ramping(self, value: int) -> None:
        """Définit le temps d'attente de rampe (WTR, 0..1000 ; ms réels = val×10+3500)."""
        if not (0 <= value <= 1000):
            raise ValueError(f"Rampe doit être entre 0 et 1000, reçu: {value}")
        self._send_command(f"WTR {value}")

    def get_wait_time_ramping(self) -> int:
        """Retourne le temps d'attente de rampe (WTR?)."""
        return self._query_int("WTR?")

    # ─────────────────────────────────────────────────────────────────────
    # Maintenance / information
    # ─────────────────────────────────────────────────────────────────────

    def get_firmware_version(self) -> str:
        """Retourne la version du firmware (FWV?), ex. '1.02.01'."""
        return self._query_value("FWV?")

    def get_serial_number(self) -> int:
        """Retourne le numéro de série (SER?)."""
        return self._query_int("SER?")

    def reset(self) -> None:
        """Réinitialise complètement le contrôleur (RST — ⚠️ perte config)."""
        self._send_command("RST")

    def set_service_mode(self, enabled: bool) -> None:
        """Active/désactive le mode service (SRV 0|1)."""
        self._send_command(f"SRV {1 if enabled else 0}")

    def get_service_mode(self) -> bool:
        """True si le mode service est activé (SRV?)."""
        return bool(self._query_int("SRV?"))

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
