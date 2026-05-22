from .ads1285 import ADS1285

try:
    from .aps import APSController
    from .wavetek import Wavetek39A
except ModuleNotFoundError:
    pass  # pyserial non installé — équipements RS-232 indisponibles

try:
    from .accelerometer import Accelerometer
except ModuleNotFoundError:
    pass  # nidaqmx non installé — accéléromètres indisponibles

__all__ = [
    "ADS1285",
    "APSController",
    "Wavetek39A",
    "Accelerometer",
]
