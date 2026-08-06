"""
Lecture des enregistrements `.dat` des unités géophone 3 axes.

Format (cf. geophones-product `docs/data-format.md`) : **miniSEED v3 (FDSN)**,
écrit par le firmware via **libmseed** (fork CAUR). Caractéristiques :
  * échantillons **int32** (ADC 24 bits signé étendu), records 4096 o ;
  * fichier = `survey-data/{survey_id}/{sn}_{YYYYMMDDTHHMMSS}.dat`, 1 record
    d'en-tête puis des records d'échantillons **par voie** ;
  * voie ADC dans l'extra-header **`caurtech.channel`** = "1" | "2" | "3" ;
  * horodatage en **nanosecondes depuis l'époque Unix (UTC)**, RTC disciplinée
    par le 1PPS GNSS.

Backend Python : **ObsPy** (qui embarque libmseed) — le format étant du miniSEED
standard, un lecteur conforme suffit. Le lecteur est **découplé** : `read_dat`
renvoie une liste de `Channel3Axis` neutres, indépendante du backend, pour qu'on
puisse basculer sur des bindings ctypes de libmseed (fork CAUR) sans toucher au
reste du banc.

⚠️ **À valider contre un vrai `.dat`** : l'accès exact aux extra-headers
`caurtech.*` via ObsPy (nom d'attribut) et le mapping voie↔trace sont marqués
TODO ci-dessous — non testables sans fichier témoin ni matériel.
"""

from dataclasses import dataclass, field

import numpy as np

# Pleine échelle des unités 3 axes : ±VREF/2 = ±2,048 V à gain 1 (VREF = 4,096 V),
# CONFIRMÉ vs datasheet ADS1285 (geophones-product/docs/bruit-plancher-v31.md).
# ⚠️ DIFFÉRENT de l'ADS1285 EVM du banc (config full_scale_vpeak = 2,5 V) : ne PAS
# réutiliser 2,5 V pour convertir les counts des .dat 3 axes. 1 LSB @ g1 ≈ 0,954 nV.
UNIT3AXIS_FULLSCALE_VPEAK_G1 = 2.048


def counts_to_volts(counts, gain: int = 1) -> np.ndarray:
    """Convertit des counts int32 (ADC 24 bits étendus) d'une unité 3 axes en volts.

    Pleine échelle ±2,048 V à gain 1, divisée par le gain PGA (le gain est dans
    l'en-tête .dat `caurtech.adc_gain` / renvoyé par CONFIG?). Sert au calcul de
    sensibilité 3 axes counts/(m/s) -> V/(m/s).
    """
    return (np.asarray(counts, dtype=np.float64)
            * (UNIT3AXIS_FULLSCALE_VPEAK_G1 / float(gain)) / (2 ** 31))


@dataclass
class Channel3Axis:
    """Une voie (axe) d'un enregistrement 3 axes, indépendante du backend."""
    channel_id: str                 # "1" | "2" | "3"
    data: np.ndarray                # échantillons int32 (counts ADC)
    start_time_ns: int              # ns depuis l'époque Unix (UTC) du 1er échantillon
    sample_rate_hz: float
    meta: dict = field(default_factory=dict)   # extra-headers caurtech.* utiles

    @property
    def sample_times_ns(self) -> np.ndarray:
        """Temps UTC (ns Unix) de chaque échantillon."""
        step = 1e9 / self.sample_rate_hz
        return self.start_time_ns + (np.arange(len(self.data)) * step).astype(np.int64)


def _channel_of_trace(tr) -> str:
    """Extrait la voie ADC d'une trace ObsPy.

    TODO(valider sur vrai .dat) : le firmware met la voie dans l'extra-header
    miniSEED v3 `caurtech.channel`. Selon la version d'ObsPy, ces extra-headers
    sont exposés différemment (ex. `tr.stats.mseed.extra_headers`). À défaut, on
    retombe sur le dernier caractère du code de canal (SID) ou l'ordre de trace.
    """
    st = getattr(tr, "stats", None)
    mseed = getattr(st, "mseed", None)
    extra = getattr(mseed, "extra_headers", None) if mseed is not None else None
    if isinstance(extra, dict):
        caur = extra.get("caurtech", {})
        if isinstance(caur, dict) and caur.get("channel"):
            return str(caur["channel"])
    # repli : dernier caractère du canal FDSN (SID) si présent
    chan = getattr(st, "channel", "") if st is not None else ""
    return chan[-1] if chan else ""


def read_dat(path: str) -> list[Channel3Axis]:
    """Lit un `.dat` miniSEED → liste de `Channel3Axis` (une par voie présente).

    Les segments d'une même voie sont concaténés dans l'ordre temporel.
    """
    try:
        import obspy
    except ImportError as e:   # noqa: F841
        raise ImportError(
            "Lecture des .dat 3 axes : ObsPy requis (embarque libmseed). "
            "Installer via l'extra du projet : pip install .[mseed] "
            "(ou basculer sur des bindings libmseed du fork CAUR)."
        )

    stream = obspy.read(path, format="MSEED")
    # Regrouper par voie (une unité 3 axes → voies "1","2","3")
    by_ch: dict[str, list] = {}
    for tr in stream:
        ch = _channel_of_trace(tr) or str(len(by_ch) + 1)
        by_ch.setdefault(ch, []).append(tr)

    channels: list[Channel3Axis] = []
    for ch, traces in sorted(by_ch.items()):
        traces.sort(key=lambda t: t.stats.starttime)
        data = np.concatenate([t.data.astype(np.int32) for t in traces])
        t0 = traces[0].stats.starttime
        # UTCDateTime -> ns Unix
        start_ns = int(round(t0.timestamp * 1e9))
        channels.append(Channel3Axis(
            channel_id=ch,
            data=data,
            start_time_ns=start_ns,
            sample_rate_hz=float(traces[0].stats.sampling_rate),
            meta={"segments": len(traces)},
        ))
    return channels
