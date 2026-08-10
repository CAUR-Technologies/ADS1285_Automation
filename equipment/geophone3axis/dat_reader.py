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

Backend Python : **simplemseed** (pur Python, lit le miniSEED **v3** FDSN). ⚠️ NE
PAS utiliser `obspy.read(format="MSEED")` : ObsPy ne gère que le miniSEED **v2** et
échoue sur ces fichiers (magic `MS\\x03`, `julday out of bounds`). Le lecteur est
**découplé** : `read_dat` renvoie une liste de `Channel3Axis` neutres, indépendante
du backend, pour pouvoir basculer sur d'autres bindings libmseed sans toucher au banc.

VALIDÉ contre un vrai `.dat` (unité CG0-000008, 2026-08-10) :
  * record d'en-tête (numSamples=0) → `caurtech.*` fichier (device_sn, geophone,
    gps_position, adc_gain, software_version, tilt…) ;
  * records de données → `caurtech.channel` = "1" | "2" | "3", samples int32 ;
  * extra-headers lus via `record.eh` (dict) — `header.extraHeadersStr` reste vide
    dans simplemseed 1.0.2, ne pas s'y fier.
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


def _caurtech(rec) -> dict:
    """Section `caurtech` de l'extra-header d'un record simplemseed (`record.eh`)."""
    eh = getattr(rec, "eh", None)
    if isinstance(eh, dict):
        caur = eh.get("caurtech")
        if isinstance(caur, dict):
            return caur
    return {}


def _start_ns(rec) -> int:
    """Instant du 1er échantillon d'un record → ns depuis l'époque Unix (UTC).

    `record.starttime` est un `datetime` aware (précision µs, suffisante à 250 Hz) ;
    le mseed3 porte la ns mais l'alignement banc se fait au 1PPS/lock-in, pas au ns.
    """
    t0 = rec.starttime
    return int(round(t0.timestamp() * 1e9))


def read_dat(path: str) -> list[Channel3Axis]:
    """Lit un `.dat` miniSEED v3 → liste de `Channel3Axis` (une par voie présente).

    Les records d'une même voie (`caurtech.channel`) sont concaténés dans l'ordre
    temporel. Le record d'en-tête (numSamples=0) fournit les métadonnées fichier
    (device_sn, geophone, gps_position, adc_gain…), recopiées dans `meta` de chaque
    voie.
    """
    try:
        import simplemseed
    except ImportError:
        raise ImportError(
            "Lecture des .dat 3 axes : simplemseed requis (miniSEED v3). "
            "Installer : pip install .[mseed]  (ObsPy ne lit PAS le miniSEED v3)."
        )

    file_meta: dict = {}
    by_ch: dict[str, list] = {}      # voie -> [(start_ns, sample_rate, samples)]
    with open(path, "rb") as fp:
        for rec in simplemseed.readMSeed3Records(fp):
            caur = _caurtech(rec)
            if rec.header.numSamples == 0:
                # Record d'en-tête fichier : métadonnées globales.
                file_meta.update(caur)
                continue
            ch = str(caur.get("channel") or (len(by_ch) + 1))
            samples = np.asarray(rec.decompress(), dtype=np.int32)
            by_ch.setdefault(ch, []).append(
                (_start_ns(rec), float(rec.header.sampleRate), samples))

    channels: list[Channel3Axis] = []
    for ch, segs in sorted(by_ch.items()):
        segs.sort(key=lambda s: s[0])
        data = np.concatenate([s[2] for s in segs])
        meta = {"segments": len(segs), "file": file_meta}
        channels.append(Channel3Axis(
            channel_id=ch,
            data=data,
            start_time_ns=segs[0][0],
            sample_rate_hz=segs[0][1],
            meta=meta,
        ))
    return channels
