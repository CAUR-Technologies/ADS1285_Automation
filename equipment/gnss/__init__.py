"""Sous-système GNSS du banc : horodatage NMEA (GPGGA) + monitoring 1PPS (NI)."""

from equipment.gnss.gnss import Gnss, parse_gpgga, nmea_checksum_ok

__all__ = ["Gnss", "parse_gpgga", "nmea_checksum_ok"]
