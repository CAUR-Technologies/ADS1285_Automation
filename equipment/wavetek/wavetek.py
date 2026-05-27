"""
Module Wavetek Model 39A — Générateur de fonction / arbitraire 40 MS/s.
Interface RS-232 via pyserial.

Protocole (Manuel opérateur 39A, réf. 1463827) :
- RS232 : 9600 baud max, 8 bits, parité aucune, 1 stop, XON/XOFF (p.59-60)
- Terminateur de commande : LF (0Ah) ; le CR (0Dh) est ignoré (p.66)
- Réponse : terminée par CR LF (0Dh 0Ah)
- Séparateur de commandes : ';'
- Commandes insensibles à la casse
- Mode non-adressable par défaut (3 fils TXD/RXD/GND) : commandes directes

IMPORTANT : le 39A n'utilise PAS le SCPI. Le jeu de commandes ci-dessous
provient du manuel (sections Remote Commands p.68-78), pas d'une supposition.
Sur l'appareil, régler REMOTE SETUP -> interface: RS232, baud: 9600.
"""

import serial
import time
from config.settings import WAVETEK_PORT, WAVETEK_BAUD, WAVETEK_TIMEOUT
from equipment.instrlog import get_logger


class Wavetek39A:
    """Contrôle le générateur Wavetek Model 39A via RS-232 (protocole natif)."""

    # Correspondance noms conviviaux -> mnémoniques WAVE du 39A (p.71)
    _WAVEFORM_MAP = {
        "sine": "SINE",
        "square": "SQUARE",
        "triangle": "TRIANG",
        "ramp": "POSRMP",        # rampe positive
        "ramp_neg": "NEGRMP",    # rampe négative
        "cosine": "COSINE",
        "sinc": "SINC",
        "haversine": "HAVSIN",
        "havercosine": "HAVCOS",
        "pulse": "PULSE",
        "dc": "DC",
    }
    WAVEFORMS = set(_WAVEFORM_MAP)

    # Terminateur de commande : LF seul (le CR est ignoré par l'instrument)
    _TERMINATOR = "\n"

    # Plages (Specifications p.4-9)
    MIN_FREQUENCY = 0.0001        # 0,1 mHz (sinus)
    MAX_FREQUENCY = 16_000_000.0  # 16 MHz (sinus)
    MIN_AMPLITUDE = 0.0
    MAX_AMPLITUDE = 20.0          # 20 Vpp circuit ouvert
    MIN_OFFSET = -10.0
    MAX_OFFSET = 10.0

    def __init__(self, port: str = WAVETEK_PORT, baud: int = WAVETEK_BAUD):
        self._port = port
        self._baud = min(baud, 9600)   # 9600 baud max (p.9)
        self._serial: serial.Serial | None = None
        self._current_waveform = "sine"
        self._log = get_logger("wavetek")

    # ─────────────────────────────────────────────────────────────────────
    # Connexion / Déconnexion
    # ─────────────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Ouvre la liaison série (XON/XOFF) et fixe les unités d'amplitude."""
        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,                # handshaking XON/XOFF requis (p.59)
            timeout=WAVETEK_TIMEOUT,
        )
        # Unités déterministes : amplitude en Vpp, niveau open-circuit (hiZ).
        self.send_command("AMPUNIT VPP")
        self.send_command("ZLOAD OPEN")
        print(f"Wavetek 39A connectée sur {self._port} (baud={self._baud}).")

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("Wavetek 39A déconnectée.")

    # ─────────────────────────────────────────────────────────────────────
    # Communication bas niveau
    # ─────────────────────────────────────────────────────────────────────

    def send_command(self, cmd: str) -> str:
        """
        Envoie une commande native 39A (terminée par LF). Pour une query
        (contenant '?'), lit et retourne la réponse (terminée CR LF).
        """
        if not self._serial or not self._serial.is_open:
            raise RuntimeError("Wavetek 39A non connectée.")
        self._serial.reset_input_buffer()
        self._serial.write((cmd + self._TERMINATOR).encode("ascii"))
        if "?" in cmd:
            resp = self._serial.readline().decode("ascii", errors="replace").strip()
            self._log.debug(f"TX {cmd!r}  ->  RX {resp!r}")
            return resp
        time.sleep(0.02)
        self._log.debug(f"TX {cmd!r}")
        return ""

    # ─────────────────────────────────────────────────────────────────────
    # Forme d'onde
    # ─────────────────────────────────────────────────────────────────────

    def set_waveform(self, waveform: str) -> None:
        """Sélectionne la forme d'onde (commande WAVE)."""
        wf = waveform.lower()
        if wf not in self._WAVEFORM_MAP:
            raise ValueError(
                f"Forme d'onde invalide : '{waveform}'. "
                f"Valides : {', '.join(sorted(self._WAVEFORM_MAP))}"
            )
        self.send_command(f"WAVE {self._WAVEFORM_MAP[wf]}")
        self._current_waveform = wf
        print(f"Forme d'onde : {self._WAVEFORM_MAP[wf]}")

    def get_waveform(self) -> str:
        return self._current_waveform

    # ─────────────────────────────────────────────────────────────────────
    # Paramètres de signal
    # ─────────────────────────────────────────────────────────────────────

    def set_frequency(self, frequency_hz: float) -> None:
        """Règle la fréquence du signal (commande WAVFREQ, en Hz)."""
        if not (self.MIN_FREQUENCY <= frequency_hz <= self.MAX_FREQUENCY):
            raise ValueError(
                f"Fréquence hors plage [{self.MIN_FREQUENCY}, "
                f"{self.MAX_FREQUENCY}] Hz : {frequency_hz}"
            )
        self.send_command(f"WAVFREQ {frequency_hz:.6f}")
        print(f"Fréquence : {frequency_hz:.4g} Hz")

    def set_amplitude(self, amplitude_vpp: float) -> None:
        """Règle l'amplitude crête-à-crête (commande AMPL, unités Vpp)."""
        if not (self.MIN_AMPLITUDE <= amplitude_vpp <= self.MAX_AMPLITUDE):
            raise ValueError(
                f"Amplitude hors plage [{self.MIN_AMPLITUDE}, "
                f"{self.MAX_AMPLITUDE}] Vpp : {amplitude_vpp}"
            )
        self.send_command(f"AMPL {amplitude_vpp:.4f}")
        print(f"Amplitude : {amplitude_vpp:.4g} Vpp")

    def set_offset(self, offset_v: float) -> None:
        """Règle l'offset DC (commande DCOFFS, en Volts)."""
        if not (self.MIN_OFFSET <= offset_v <= self.MAX_OFFSET):
            raise ValueError(
                f"Offset hors plage [{self.MIN_OFFSET}, "
                f"{self.MAX_OFFSET}] V : {offset_v}"
            )
        self.send_command(f"DCOFFS {offset_v:.4f}")
        print(f"Offset : {offset_v:.4g} V")

    # ─────────────────────────────────────────────────────────────────────
    # Sortie
    # ─────────────────────────────────────────────────────────────────────

    def enable_output(self) -> None:
        """Active la sortie principale (OUTPUT ON)."""
        self.send_command("OUTPUT ON")
        print("Sortie : ON")

    def disable_output(self) -> None:
        """Désactive la sortie principale (OUTPUT OFF)."""
        self.send_command("OUTPUT OFF")
        print("Sortie : OFF")

    # ─────────────────────────────────────────────────────────────────────
    # Identification / maintenance
    # ─────────────────────────────────────────────────────────────────────

    def identify(self) -> str:
        """Identification (*IDN?) : <NAME>, <model>, 0, <version> (p.75)."""
        return self.send_command("*IDN?")

    def reset(self) -> None:
        """Réinitialise aux défauts usine (*RST)."""
        self.send_command("*RST")
        self._current_waveform = "sine"
        print("Instrument réinitialisé (*RST)")

    def beep(self) -> None:
        """Émet un bip (commande BEEP)."""
        self.send_command("BEEP")

    def local(self) -> None:
        """Rend le contrôle local et déverrouille le clavier (LOCAL)."""
        self.send_command("LOCAL")

    # ─────────────────────────────────────────────────────────────────────
    # Séquence courante
    # ─────────────────────────────────────────────────────────────────────

    def configure_frequency_sweep(
        self, frequencies: list[float], amplitude: float = 1.0, waveform: str = "sine"
    ):
        """Configure et balaie une liste de fréquences (pas discrets)."""
        self.set_waveform(waveform)
        self.set_amplitude(amplitude)
        self.set_offset(0.0)
        self.enable_output()
        print(f"Balayage fréquentiel : {len(frequencies)} fréquences")
        for freq in frequencies:
            self.set_frequency(freq)
            yield freq

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        try:
            self.disable_output()
        finally:
            self.disconnect()

    def __repr__(self) -> str:
        return (
            f"Wavetek39A(port='{self._port}', baud={self._baud}, "
            f"connected={self._serial is not None and self._serial.is_open})"
        )
