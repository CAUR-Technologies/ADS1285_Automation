"""
Journal unifié du banc -> logs/bench_<date>_<heure>.log (un par exécution).

Une seule destination, avec une colonne 'source' (APS, Wavetek, ADS1285,
TestBench, GUI…). Trace les échanges (TX/RX, niveau DEBUG) et surtout les
erreurs de toute part (niveau ERROR, avec traceback via exc_info).

Format : HH:MM:SS.mmm  <source>  <niveau>  <message>

Note : le bridge 32-bit (processus séparé) conserve son propre
bridge/bridge32.log — il ne partage pas ce process.
"""

import os
import logging
from datetime import datetime

_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
# Un nouveau fichier horodaté par exécution (pas de ':' — interdit sous Windows).
_LOG_FILE = os.path.join(
    _LOG_DIR, datetime.now().strftime("bench_%Y-%m-%d_%H-%M-%S.log"))
_ROOT_NAME = "bench"
_configured = False


class _DefaultSourceFilter(logging.Filter):
    """Garantit qu'un enregistrement a toujours un attribut 'source'."""
    def filter(self, record):
        if not hasattr(record, "source"):
            record.source = "-"
        return True


def _ensure_configured() -> logging.Logger:
    global _configured
    root = logging.getLogger(_ROOT_NAME)
    if not _configured:
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
            handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s.%(msecs)03d  %(source)-9s  %(levelname)-5s  %(message)s",
                datefmt="%H:%M:%S"))
            handler.addFilter(_DefaultSourceFilter())
            root.addHandler(handler)
            root.setLevel(logging.DEBUG)
            root.propagate = False
        except Exception:
            root.addHandler(logging.NullHandler())
            root.propagate = False
        _configured = True
    return root


def get_logger(source: str) -> logging.LoggerAdapter:
    """
    Retourne un logger écrivant dans le journal unifié logs/bench.log,
    étiqueté par <source>.

    Usage :
        log = get_logger("APS")
        log.debug("TX 'STF 20' -> RX 'STF OK'")
        log.error("liaison perdue", exc_info=exc)
    """
    return logging.LoggerAdapter(_ensure_configured(), {"source": source})
