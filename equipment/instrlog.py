"""
Journalisation légère des échanges instruments (commandes TX / réponses RX).

Écrit dans logs/<nom>.log avec horodatage. Utile pour déboguer les liaisons
série (APS 0109, Wavetek) : on voit exactement ce qui est envoyé/reçu et quand
(ex. repérer une bannière de reboot 'Mega64' et son instant).
"""

import os
import logging

_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger écrivant dans logs/<name>.log (créé au besoin)."""
    logger = logging.getLogger(f"instr.{name}")
    if not logger.handlers:
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
            handler = logging.FileHandler(
                os.path.join(_LOG_DIR, f"{name}.log"), encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s.%(msecs)03d  %(message)s",
                                  datefmt="%H:%M:%S"))
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
        except Exception:
            # En cas d'échec (droits, etc.) : logger inerte plutôt que planter
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
    return logger
