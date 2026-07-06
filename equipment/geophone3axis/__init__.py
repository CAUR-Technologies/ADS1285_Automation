"""Client USB (CDC-ACM) des unités géophone 3 axes pour le banc de calibration."""

from equipment.geophone3axis.geophone3axis import (
    Geophone3Axis,
    discover_units,
    GEOPHONE3AXIS_VID,
    GEOPHONE3AXIS_PID,
)

__all__ = ["Geophone3Axis", "discover_units",
           "GEOPHONE3AXIS_VID", "GEOPHONE3AXIS_PID"]
