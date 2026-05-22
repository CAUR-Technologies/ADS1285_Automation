"""
Module Wavetek Model 39A — Générateur de fonction
Interface RS-232 via pyserial selon le protocole SCPI-like.

Protocole :
- Baud : 9600 (configurable)
- Bits : 8, Parité : aucune, Stop : 1
- Terminaison : \\r\\n (CRLF)
- Commandes : syntaxe SCPI-like (ex: FUNC SINE, FREQ 1000.0)
"""

import serial
import time
from config.settings import WAVETEK_PORT, WAVETEK_BAUD, WAVETEK_TIMEOUT


class Wavetek39A:
    """Contrôle le générateur de fonction Wavetek Model 39A via RS-232."""

    # Formes d'onde supportées
    WAVEFORMS = {"sine", "square", "triangle", "ramp", "pulse", "noise", "dc"}

    # Protocole
    _TERMINATOR = "\r\n"

    # Plages typiques
    MIN_FREQUENCY = 0.1
    MAX_FREQUENCY = 10000.0
    MIN_AMPLITUDE = 0.0
    MAX_AMPLITUDE = 10.0
    MIN_OFFSET = -5.0
    MAX_OFFSET = 5.0

    def __init__(self, port: str = WAVETEK_PORT, baud: int = WAVETEK_BAUD):
        """
        Parameters
        ----------
        port : str
            Port COM (ex: "COM5")
        baud : int
            Vitesse en bauds (défaut : 9600)
        """
        self._port = port
        self._baud = baud
        self._serial: serial.Serial | None = None
        self._current_waveform = "sine"

    # ─────────────────────────────────────────────────────────────────────
    # Connexion / Déconnexion
    # ─────────────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Établit la connexion série avec la Wavetek 39A."""
        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=WAVETEK_TIMEOUT,
        )
        print(f"Wavetek 39A connectée sur {self._port} (baud={self._baud}).")

    def disconnect(self) -> None:
        """Ferme la connexion série."""
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("Wavetek 39A déconnectée.")

    # ─────────────────────────────────────────────────────────────────────
    # Protocole de communication bas niveau
    # ─────────────────────────────────────────────────────────────────────

    def send_command(self, cmd: str) -> str:
        """
        Envoie une commande SCPI et retourne la réponse.

        La commande est automatiquement terminée par \\r\\n.

        Parameters
        ----------
        cmd : str
            Commande SCPI (ex: "FUNC SINE", "FREQ 1000", "OUTP ON")

        Returns
        -------
        str
            Réponse de l'instrument (vide pour commandes sans query)
        """
        if not self._serial or not self._serial.is_open:
            raise RuntimeError("Wavetek 39A non connectée.")

        # Envoyer la commande avec terminaison CRLF
        msg = cmd + self._TERMINATOR
        self._serial.write(msg.encode('ascii'))
        time.sleep(0.05)

        # Lire la réponse (jusqu'à timeout ou fin de ligne)
        response = b""
        while True:
            byte = self._serial.read(1)
            if not byte or byte == b"\n":
                break
            if byte != b"\r":
                response += byte

        return response.decode('ascii', errors='replace').strip()

    # ─────────────────────────────────────────────────────────────────────
    # Sélection et contrôle de forme d'onde
    # ─────────────────────────────────────────────────────────────────────

    def set_waveform(self, waveform: str) -> None:
        """Sélectionne la forme d'onde.

        Parameters
        ----------
        waveform : str
            Forme d'onde : "sine", "square", "triangle", "ramp", "pulse", "noise", "dc"
        """
        wf = waveform.lower()
        if wf not in self.WAVEFORMS:
            raise ValueError(
                f"Forme d'onde invalide : '{waveform}'. "
                f"Valides : {', '.join(sorted(self.WAVEFORMS))}"
            )
        self.send_command(f"FUNC {wf.upper()}")
        self._current_waveform = wf
        print(f"Forme d'onde : {wf.upper()}")

    def get_waveform(self) -> str:
        """Retourne la forme d'onde actuelle (depuis la cache locale)."""
        return self._current_waveform

    # ─────────────────────────────────────────────────────────────────────
    # Paramètres de signal
    # ─────────────────────────────────────────────────────────────────────

    def set_frequency(self, frequency_hz: float) -> None:
        """Règle la fréquence.

        Parameters
        ----------
        frequency_hz : float
            Fréquence en Hz (0.1 .. 10000)
        """
        if not (self.MIN_FREQUENCY <= frequency_hz <= self.MAX_FREQUENCY):
            raise ValueError(
                f"Fréquence doit être entre {self.MIN_FREQUENCY} et "
                f"{self.MAX_FREQUENCY} Hz, reçu: {frequency_hz}"
            )
        self.send_command(f"FREQ {frequency_hz:.6f}")
        print(f"Fréquence : {frequency_hz:.2f} Hz")

    def set_amplitude(self, amplitude_vpp: float) -> None:
        """Règle l'amplitude crête-à-crête.

        Parameters
        ----------
        amplitude_vpp : float
            Amplitude en Volts peak-to-peak (0 .. 10)
        """
        if not (self.MIN_AMPLITUDE <= amplitude_vpp <= self.MAX_AMPLITUDE):
            raise ValueError(
                f"Amplitude doit être entre {self.MIN_AMPLITUDE} et "
                f"{self.MAX_AMPLITUDE} Vpp, reçu: {amplitude_vpp}"
            )
        self.send_command(f"VOLT {amplitude_vpp:.4f} VPP")
        print(f"Amplitude : {amplitude_vpp:.2f} Vpp")

    def set_offset(self, offset_v: float) -> None:
        """Règle l'offset DC (décalage en tension continue).

        Parameters
        ----------
        offset_v : float
            Offset en Volts (-5 .. +5)
        """
        if not (self.MIN_OFFSET <= offset_v <= self.MAX_OFFSET):
            raise ValueError(
                f"Offset doit être entre {self.MIN_OFFSET} et "
                f"{self.MAX_OFFSET} V, reçu: {offset_v}"
            )
        self.send_command(f"VOLT:OFFS {offset_v:.4f}")
        print(f"Offset : {offset_v:.2f} V")

    # ─────────────────────────────────────────────────────────────────────
    # Contrôle de sortie
    # ─────────────────────────────────────────────────────────────────────

    def enable_output(self) -> None:
        """Active la sortie du signal."""
        self.send_command("OUTP ON")
        print("Sortie : ON")

    def disable_output(self) -> None:
        """Désactive la sortie du signal."""
        self.send_command("OUTP OFF")
        print("Sortie : OFF")

    # ─────────────────────────────────────────────────────────────────────
    # Identification et maintenance
    # ─────────────────────────────────────────────────────────────────────

    def identify(self) -> str:
        """Retourne l'identification de l'instrument (query *IDN?).

        Returns
        -------
        str
            Chaîne d'identification (ex: "Wavetek 39A")
        """
        return self.send_command("*IDN?")

    def reset(self) -> None:
        """Réinitialise l'instrument à l'état par défaut (*RST).

        Réinitialise tous les paramètres aux valeurs par défaut :
        - Forme d'onde : SINE
        - Fréquence : 1 kHz
        - Amplitude : 5V
        - Offset : 0V
        - Sortie : ON
        """
        self.send_command("*RST")
        self._current_waveform = "sine"
        print("Instrument réinitialisé")

    # ─────────────────────────────────────────────────────────────────────
    # Séquences courantes
    # ─────────────────────────────────────────────────────────────────────

    def configure_frequency_sweep(
        self, frequencies: list[float], amplitude: float = 1.0, waveform: str = "sine"
    ) -> None:
        """Configure l'instrument pour un balayage fréquentiel.

        Parameters
        ----------
        frequencies : list[float]
            Liste des fréquences à balayer (Hz)
        amplitude : float
            Amplitude du signal (Vpp), défaut 1.0V
        waveform : str
            Forme d'onde, défaut "sine"

        Example
        -------
        with Wavetek39A() as gen:
            gen.configure_frequency_sweep(
                frequencies=[1, 2, 5, 10, 20, 50, 100],
                amplitude=2.0,
                waveform="sine"
            )
            gen.enable_output()
            # ... acquisition ...
        """
        self.set_waveform(waveform)
        self.set_amplitude(amplitude)
        self.set_offset(0.0)
        self.enable_output()

        print(f"Balayage fréquentiel : {len(frequencies)} fréquences")
        for freq in frequencies:
            self.set_frequency(freq)
            yield freq  # Permet une utilisation en générateur

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        """Entre le context manager (connexion automatique)."""
        self.connect()
        return self

    def __exit__(self, *args):
        """Sort le context manager (déconnexion automatique)."""
        self.disable_output()
        self.disconnect()

    # ─────────────────────────────────────────────────────────────────────
    # Représentation
    # ─────────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Wavetek39A(port='{self._port}', baud={self._baud}, "
            f"connected={self._serial is not None and self._serial.is_open})"
        )
