"""
GNSS du banc — horodatage par trames NMEA GPGGA (port série VCP).

Le récepteur GNSS expose un port COM virtuel (VCP) qui émet des trames NMEA.
On exploite **GPGGA** (heure UTC, qualité de fix, satellites, altitude) pour
horodater les mesures du banc et corréler l'heure du banc à celle du GNSS (avec,
en Phase 2b, le 1PPS câblé sur une voie numérique de la carte NI pour l'alignement
fin à la seconde GPS).

⚠️ GPGGA ne contient que l'heure du JOUR (hhmmss.sss), PAS la date. Pour un
horodatage absolu complet, la date est prise sur l'horloge système (ou via une
trame GPRMC/GPZDA si ajoutée plus tard). Pour la corrélation intra-journée avec
l'unité 3 axes, l'heure du jour + le 1PPS suffisent.
"""

import threading
import time

import serial


def nmea_checksum_ok(sentence: str) -> bool:
    """Valide le checksum NMEA ('$....*HH'). Tolère l'absence de checksum."""
    s = sentence.strip()
    if not s.startswith("$") or "*" not in s:
        return False
    body, _, cksum = s[1:].partition("*")
    try:
        want = int(cksum[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


def parse_gpgga(sentence: str) -> dict | None:
    """Parse une trame GPGGA (ou GNGGA) → dict, ou None si non-GGA / invalide.

    Champs GGA : 1=UTC hhmmss.sss, 2/3=lat, 4/5=lon, 6=qualité fix
    (0=invalide,1=GPS,2=DGPS,4=RTK fix,5=RTK float...), 7=nb satellites,
    8=HDOP, 9=altitude (m).
    """
    s = sentence.strip()
    if "GGA" not in s[:7]:
        return None
    if "*" in s and not nmea_checksum_ok(s):
        return None
    f = s.split(",")
    if len(f) < 10:
        return None

    def _f(x):
        try:
            return float(x)
        except (ValueError, TypeError):
            return None

    utc = f[1]  # hhmmss.sss
    t_sod = None  # secondes depuis minuit UTC
    if len(utc) >= 6:
        try:
            hh, mm, ss = int(utc[0:2]), int(utc[2:4]), float(utc[4:])
            t_sod = hh * 3600 + mm * 60 + ss
        except ValueError:
            t_sod = None
    try:
        fix_q = int(f[6]) if f[6] else 0
    except ValueError:
        fix_q = 0
    try:
        n_sat = int(f[7]) if f[7] else 0
    except ValueError:
        n_sat = 0
    return {
        "utc_hhmmss": utc,
        "utc_sod": t_sod,          # secondes-depuis-minuit UTC (float)
        "fix_quality": fix_q,      # 0 = pas de fix
        "num_sats": n_sat,
        "hdop": _f(f[8]),
        "altitude_m": _f(f[9]),
    }


class Gnss:
    """Récepteur GNSS sur VCP série — lit les trames NMEA GPGGA.

    Utilisable en polling (`read_fix`) ou en tâche de fond (`start_polling`)
    qui maintient `last_fix` à jour.
    """

    def __init__(self, port: str, baud: int = 9600, timeout: float = 1.0):
        self._port = port
        self._baud = baud
        self._timeout = timeout
        self._ser: serial.Serial | None = None
        self.last_fix: dict | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def connect(self) -> None:
        self._ser = serial.Serial(self._port, self._baud, timeout=self._timeout)
        print(f"GNSS connecté sur {self._port} (baud={self._baud}).")

    def disconnect(self) -> None:
        self.stop_polling()
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
        self._ser = None
        print("GNSS déconnecté.")

    def read_fix(self, timeout: float = 3.0) -> dict | None:
        """Lit les trames jusqu'à une GPGGA valide (ou timeout). Met à jour
        `last_fix`. Retourne le fix (dict) ou None si aucune GGA à temps."""
        if self._ser is None:
            raise RuntimeError("GNSS non connecté.")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._ser.readline().decode("ascii", errors="replace")
            except serial.SerialException:
                break
            fix = parse_gpgga(line)
            if fix is not None:
                self.last_fix = fix
                return fix
        return None

    def has_fix(self) -> bool:
        """True si le dernier fix connu est valide (fix_quality > 0)."""
        return bool(self.last_fix and self.last_fix.get("fix_quality", 0) > 0)

    def utc_sod(self) -> float | None:
        """Dernière heure UTC connue en secondes-depuis-minuit (ou None)."""
        return self.last_fix.get("utc_sod") if self.last_fix else None

    # ---- tâche de fond -------------------------------------------------
    def start_polling(self, period_s: float = 1.0) -> None:
        """Maintient `last_fix` à jour en arrière-plan (thread daemon)."""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop.clear()

        def _loop():
            while not self._stop.is_set():
                self.read_fix(timeout=period_s + 1.0)
                self._stop.wait(period_s)

        self._poll_thread = threading.Thread(target=_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
