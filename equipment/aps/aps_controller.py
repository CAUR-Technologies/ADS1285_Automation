"""
Module APS 0109 — Contrôleur de position SPEKTRA
Interface RS-232 via pyserial selon le protocole APS 0109.
Deux axes disponibles : VERTICAL et HORIZONTAL.

Protocole :
- Baud : 19200 (configurable)
- Bits : 8, Parité : aucune, Stop : 1
- Terminaison : \\x00 (null byte, $0)
- Réponse OK : "COMMANDE OK"
- Réponse erreur : "ERR" (détail via GES)
"""

import serial
import time
from config.settings import (
    APS_CONTROLLER_VERTICAL_PORT,
    APS_CONTROLLER_HORIZONTAL_PORT,
    APS_BAUD,
    APS_TIMEOUT,
)


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
    _SUCCESS_RESPONSE = "COMMANDE OK"
    _ERROR_RESPONSE = "ERR"

    def __init__(self, axis: str, port: str | None = None, baud: int = APS_BAUD):
        """
        Parameters
        ----------
        axis : str
            "vertical" ou "horizontal"
        port : str, optional
            Port COM à utiliser. Si None, utilise le port par défaut du settings.
        baud : int
            Vitesse en bauds (défaut : 9600, utilisé 19200 en matériel)
        """
        if axis not in (self.VERTICAL, self.HORIZONTAL):
            raise ValueError(f"Axe invalide : '{axis}'. Utiliser 'vertical' ou 'horizontal'.")
        self._axis = axis
        self._port = port or self._DEFAULT_PORTS[axis]
        self._baud = baud
        self._serial: serial.Serial | None = None

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
        print(f"APS 0109 [{self._axis}] connecté sur {self._port} (baud={self._baud}).")

    def disconnect(self) -> None:
        """Ferme la connexion série."""
        if self._serial and self._serial.is_open:
            self._serial.close()
        print(f"APS 0109 [{self._axis}] déconnecté.")

    # ─────────────────────────────────────────────────────────────────────
    # Protocol de communication bas niveau
    # ─────────────────────────────────────────────────────────────────────

    def _send_raw(self, cmd: str) -> str:
        """
        Envoie une commande brute et retourne la réponse.

        La commande est terminée par \\x00 selon le protocole APS 0109.
        """
        if not self._serial or not self._serial.is_open:
            raise RuntimeError(f"APS 0109 [{self._axis}] non connecté.")

        # Envoyer la commande avec terminaison null byte
        msg = (cmd + "\x00").encode('ascii')
        self._serial.write(msg)
        time.sleep(0.05)

        # Lire la réponse (jusqu'à null byte ou timeout)
        response = b""
        while True:
            byte = self._serial.read(1)
            if not byte or byte == b"\x00":
                break
            response += byte

        return response.decode('ascii', errors='replace').strip()

    def _send_command(self, cmd: str, expect_ok: bool = True) -> str:
        """
        Envoie une commande et valide la réponse.

        Lève une RuntimeError si expect_ok=True et la réponse est une erreur.
        """
        response = self._send_raw(cmd)

        if expect_ok and response == self._ERROR_RESPONSE:
            error_detail = self.get_last_error()
            raise RuntimeError(f"Erreur APS 0109 [{self._axis}]: {error_detail}")

        return response

    # ─────────────────────────────────────────────────────────────────────
    # Gestion des erreurs
    # ─────────────────────────────────────────────────────────────────────

    def get_last_error(self) -> str:
        """Retourne le dernier message d'erreur."""
        return self._send_raw("GES")

    # ─────────────────────────────────────────────────────────────────────
    # Commandes de contrôle de position
    # ─────────────────────────────────────────────────────────────────────

    def set_zero_position(self, value: int) -> None:
        """Définit la position zéro.

        Parameters
        ----------
        value : int
            Valeur zéro (-99..99)
        """
        if not (-99 <= value <= 99):
            raise ValueError(f"Zéro position doit être entre -99 et 99, reçu: {value}")
        self._send_command(f"ZER {value}")

    def get_zero_position(self) -> int:
        """Retourne la position zéro."""
        resp = self._send_command("ZER?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue ZER?: {resp}")

    def set_position(self, position: float) -> None:
        """Positionne la table.

        Note : Les commandes de positionnement direct ne sont pas documentées
        dans le protocole APS 0109. Utiliser start()/stop() pour le contrôle.
        """
        raise NotImplementedError(
            "APS 0109 n'a pas de commande de positionnement direct. "
            "Utiliser start() pour lancer le mouvement contrôlé."
        )

    # ─────────────────────────────────────────────────────────────────────
    # Commandes de contrôle du contrôleur
    # ─────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le contrôleur."""
        self._send_command("STA")

    def get_start_status(self) -> bool:
        """Retourne True si le contrôleur est en marche."""
        resp = self._send_command("STA?", expect_ok=False)
        try:
            return bool(int(resp))
        except ValueError:
            raise RuntimeError(f"Réponse inattendue STA?: {resp}")

    def stop(self) -> None:
        """Arrête le contrôleur."""
        self._send_command("STP")

    def get_stop_status(self) -> str:
        """Retourne l'état d'arrêt."""
        return self._send_command("STP?", expect_ok=False)

    # ─────────────────────────────────────────────────────────────────────
    # Paramètres de rigidité (stiffness)
    # ─────────────────────────────────────────────────────────────────────

    def set_stiffness(self, value: int) -> None:
        """Définit la rigidité.

        Parameters
        ----------
        value : int
            Rigidité (0..31)
        """
        if not (0 <= value <= 31):
            raise ValueError(f"Rigidité doit être entre 0 et 31, reçu: {value}")
        self._send_command(f"STF {value}")

    def get_stiffness(self) -> int:
        """Retourne la rigidité actuelle."""
        resp = self._send_command("STF?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue STF?: {resp}")

    def set_stiffness_start_value(self, value: int) -> None:
        """Définit la valeur de démarrage de rigidité.

        Parameters
        ----------
        value : int
            Valeur de démarrage (0..31)
        """
        if not (0 <= value <= 31):
            raise ValueError(f"Rigidité de démarrage doit être entre 0 et 31, reçu: {value}")
        self._send_command(f"SSS {value}")

    def get_stiffness_start_value(self) -> int:
        """Retourne la valeur de démarrage de rigidité."""
        resp = self._send_command("SSS?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue SSS?: {resp}")

    # ─────────────────────────────────────────────────────────────────────
    # Paramètres de limites de position
    # ─────────────────────────────────────────────────────────────────────

    def set_position_max(self, value: int) -> None:
        """Définit la position maximale (LED).

        Parameters
        ----------
        value : int
            Position max (0..1023)
        """
        if not (0 <= value <= 1023):
            raise ValueError(f"Position max doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"PMA {value}")

    def get_position_max(self) -> int:
        """Retourne la position maximale."""
        resp = self._send_command("PMA?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue PMA?: {resp}")

    def set_position_min(self, value: int) -> None:
        """Définit la position minimale (LED).

        Parameters
        ----------
        value : int
            Position min (0..1023)
        """
        if not (0 <= value <= 1023):
            raise ValueError(f"Position min doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"PMI {value}")

    def get_position_min(self) -> int:
        """Retourne la position minimale."""
        resp = self._send_command("PMI?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue PMI?: {resp}")

    # ─────────────────────────────────────────────────────────────────────
    # Paramètres de sécurité et de mouvement
    # ─────────────────────────────────────────────────────────────────────

    def set_overtravel_tolerance(self, value: int) -> None:
        """Définit la tolérance de surcoure.

        Parameters
        ----------
        value : int
            Tolérance (0..1023)
        """
        if not (0 <= value <= 1023):
            raise ValueError(f"Tolérance doit être entre 0 et 1023, reçu: {value}")
        self._send_command(f"OTT {value}")

    def get_overtravel_tolerance(self) -> int:
        """Retourne la tolérance de surcoure."""
        resp = self._send_command("OTT?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue OTT?: {resp}")

    def set_wait_time_ramping(self, value: int) -> None:
        """Définit le temps d'attente de rampe.

        Temps réel en ms = value × 10 + 3500

        Parameters
        ----------
        value : int
            Valeur de rampe (0..1000)
        """
        if not (0 <= value <= 1000):
            raise ValueError(f"Rampe doit être entre 0 et 1000, reçu: {value}")
        self._send_command(f"WTR {value}")

    def get_wait_time_ramping(self) -> int:
        """Retourne le temps d'attente de rampe."""
        resp = self._send_command("WTR?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue WTR?: {resp}")

    # ─────────────────────────────────────────────────────────────────────
    # Commandes de maintenance et information
    # ─────────────────────────────────────────────────────────────────────

    def get_firmware_version(self) -> str:
        """Retourne la version du firmware."""
        return self._send_command("FWV?", expect_ok=False)

    def get_serial_number(self) -> int:
        """Retourne le numéro de série."""
        resp = self._send_command("SER?", expect_ok=False)
        try:
            return int(resp)
        except ValueError:
            raise RuntimeError(f"Réponse inattendue SER?: {resp}")

    def reset(self) -> None:
        """Réinitialise complètement le contrôleur (perte de configuration).

        ⚠️ ATTENTION : Cette commande efface la configuration !
        """
        self._send_command("RST")

    def set_service_mode(self, enabled: bool) -> None:
        """Active/désactive le mode service.

        Parameters
        ----------
        enabled : bool
            True pour activer, False pour désactiver
        """
        value = 1 if enabled else 0
        self._send_command(f"SRV {value}")

    def get_service_mode(self) -> bool:
        """Retourne True si le mode service est activé."""
        resp = self._send_command("SRV?", expect_ok=False)
        try:
            return bool(int(resp))
        except ValueError:
            raise RuntimeError(f"Réponse inattendue SRV?: {resp}")

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
