"""
Orchestration d'une caractérisation d'unité géophone 3 axes (SQUELETTE).

Le banc pilote une unité 3 axes auto-enregistreuse (USB CDC) et corrèle ses 3
voies avec l'accéléromètre de référence, sur une base de temps GPS commune :

    1. configure l'unité         : unit.set_config(...)
    2. START + SYNC              : l'unité enregistre sur µSD, marqueur temps
    3. excitation shaker         + acquisition accéléro réf. + capture 1PPS (NI)
    4. STOP                      : fin d'enregistrement unité
    5. LS / GET                  : récupération des .dat (miniSEED)
    6. parse .dat + CORRÉLATION  : aligne par temps GPS -> sensibilité 3 axes

Ce qui est **réel** ici : le pilotage de l'unité (2/4/5), le GNSS et le PPS.
Ce qui est **TODO** (nécessite matériel + un vrai .dat pour valider) :
  * l'acquisition accéléro CONTINUE co-synchronisée avec le compteur 1PPS pendant
    tout le balayage (l'accéléro fait aujourd'hui des fenêtres finies par point) ;
  * la corrélation (parse miniSEED via dat_reader -> alignement temps GPS ->
    lock-in par fréquence -> sensibilité counts/(m/s) par voie).

Voir [[../gnss/pps.py]] (temps GPS par échantillon) et [[dat_reader.py]].
"""

import os
import threading
import time

import numpy as np

from equipment.geophone3axis.geophone3axis import Geophone3Axis
from equipment.geophone3axis import dat_reader
from equipment.dsp import (coherent_phasor, coherent_amplitude_peak,
                           coherent_phasor_at_times, snr_db, thd_percent, G_ACCEL)


class Characterize3AxisSession:
    """Enchaîne une caractérisation 3 axes autour d'une excitation shaker.

    Paramètres :
      bench : TestBench (shaker + accéléromètre de référence)
      unit  : Geophone3Axis (unité sous test, USB CDC)
      gnss  : Gnss (heure UTC via NMEA GPGGA)
      pps   : Pps1ppsMonitor (fronts 1PPS -> indices d'échantillon AI)
      data_dir : dossier de récupération des .dat
    """

    def __init__(self, bench, unit: Geophone3Axis, gnss, pps, data_dir: str):
        self.bench = bench
        self.unit = unit
        self.gnss = gnss
        self.pps = pps
        self.data_dir = data_dir
        self._pulled: list[str] = []

    # ---- 1-2 : préparer et démarrer l'unité ----------------------------
    def prepare_unit(self, unit_config: dict) -> dict:
        """Applique la config à l'unité et retourne son CONFIG? effectif."""
        self.unit.connect()
        self.unit.set_config(unit_config)
        return self.unit.config()

    def start_unit(self) -> None:
        """Démarre l'enregistrement de l'unité + marqueur de synchro."""
        self.unit.start()
        self.unit.sync()   # marqueur temporel pour l'alignement GPS

    def stop_unit(self) -> None:
        self.unit.stop()

    # ---- 3 : excitation + acquisition co-synchronisée ------------------
    def run_excitation(self, freqs, *, dwell_s: float = 8.0,
                       ai_rate: int = 2000, sens_v_per_g: float | None = None) -> dict:
        """CHEMIN .dat + GPS — balaye le shaker en enregistrant l'accéléromètre de
        référence **EN CONTINU**, co-synchronisé au **1PPS ProPak (temps GPS)** via
        `Pps1ppsMonitor`, pendant que l'unité enregistre ses `.dat`. Chaque palier
        de fréquence est daté en temps GPS (sod) → `schedule` pour `correlate()`.

        L'accéléro tourne en acquisition **continue** (il génère `ai/SampleClock`,
        que le compteur PPS latche à chaque front 1PPS sur PFI0). On draine
        périodiquement les échantillons AI et les fronts 1PPS, et on étiquette
        chaque front avec la seconde UTC du GNSS (GPGGA) → temps GPS par échantillon.

        Retour : {ref_signal (V), ref_sods (s, temps GPS/échantillon), schedule
                 (avec sod_start/sod_end par palier), ai_rate, sens_v_per_g}.

        ⚠️ Matériel complet requis (accéléro NI + 1PPS ProPak sur PFI0 + GNSS NMEA)
        et unité en cours d'enregistrement (`start_unit`). Balaye HAUTE→BASSE
        (sécurité anti-butée). À VALIDER au banc — la corrélation, elle, est testée.
        """
        import time as _t
        import numpy as _np
        import nidaqmx
        from nidaqmx.constants import (AcquisitionType, TerminalConfiguration,
                                       READ_ALL_AVAILABLE)
        from equipment.gnss.pps import sample_to_gps_sod

        accel = self.bench._accel
        ref_idx = self.bench._ref_channel
        ch_name = accel._channels[ref_idx]
        if sens_v_per_g is None:
            sens_v_per_g = accel.sensitivity_v_per_g

        ai = nidaqmx.Task()
        ai.ai_channels.add_ai_voltage_chan(
            f"{accel._device}/{ch_name}",
            terminal_config=TerminalConfiguration.RSE, min_val=-10.0, max_val=10.0)
        ai.timing.cfg_samp_clk_timing(rate=ai_rate, sample_mode=AcquisitionType.CONTINUOUS)

        ref: list = []                       # échantillons volts (continu)
        edge_idx: list = []                  # indices AI des fronts 1PPS
        edge_sod: list = []                  # seconde UTC entière de chaque front
        schedule: list = []

        def _drain():
            data = ai.read(number_of_samples_per_channel=READ_ALL_AVAILABLE)
            if data:
                ref.extend(data if isinstance(data, list) else [data])
            for s in self.pps.read_edges():
                if self.gnss is not None:
                    self.gnss.read_fix(timeout=0.2)
                    sod = self.gnss.utc_sod()
                    if sod is not None:
                        edge_idx.append(int(s))
                        edge_sod.append(round(sod))   # le front 1PPS = frontière de seconde

        self.pps.start()
        ai.start()
        try:
            _t.sleep(0.5); _drain()          # amorçage
            for f in sorted(freqs, reverse=True):    # HAUTE→BASSE (anti-butée)
                self.bench._check_stop()
                exc = self.bench.set_frequency_safe(f)
                if exc.get("skipped"):
                    continue
                _drain(); i0 = len(ref)
                _t.sleep(dwell_s)
                _drain(); i1 = len(ref)
                schedule.append({"freq_hz": f, "sample_start": i0, "sample_end": i1})
        finally:
            try:
                self.bench._safe_shutdown()
            except Exception:               # noqa: BLE001
                pass
            _drain()
            self.pps.stop()
            ai.stop(); ai.close()

        n = len(ref)
        if edge_idx and edge_sod:
            ref_sods = _np.array(
                [sample_to_gps_sod(i, edge_idx, edge_sod, ai_rate) for i in range(n)],
                dtype=float)
        else:
            # Pas de 1PPS/GNSS exploitable → base de temps locale (magnitude seule).
            ref_sods = _np.arange(n) / float(ai_rate)
        for seg in schedule:
            a = min(seg["sample_start"], n - 1) if n else 0
            b = min(seg["sample_end"] - 1, n - 1) if n else 0
            seg["sod_start"] = float(ref_sods[a]) if n else 0.0
            seg["sod_end"] = float(ref_sods[b]) if n else 0.0
        return {"ref_signal": _np.asarray(ref, dtype=float), "ref_sods": ref_sods,
                "schedule": schedule, "ai_rate": ai_rate, "sens_v_per_g": sens_v_per_g}

    # ---- 3bis : voie STREAM (contourne le bug firmware GET>2 Ko) -------
    # Tant que GET est cassé pour les .dat soutenus, on caractérise sur le flux
    # live `STREAM ON GEO` (3 voies, ~50 Hz → bande utile 0,1–20 Hz). L'excitation
    # étant un sinus stationnaire, le lock-in mono-bin extrait l'amplitude de
    # CHAQUE voie indépendamment : pas besoin d'alignement échantillon-exact, une
    # simple co-acquisition sur la même fenêtre murale suffit pour la sensibilité
    # (magnitude). Le temps GPS/1PPS reste requis pour la PHASE absolue et la voie
    # .dat archivable — non nécessaire ici.

    def _accel_fs_for(self, freq_hz: float, duration_s: float) -> int:
        """Taux d'échantillonnage accéléro adapté à la fréquence (cf. testbench).

        ~50×f (min 200 Hz), plafonné au taux NI et à ~50 k échantillons (sinon en
        BF la fenêtre × plein taux ferait une acquisition DAQmx énorme)."""
        accel = self.bench._accel
        fs = int(min(max(freq_hz * 50.0, 200.0), accel.sample_rate))
        if fs * duration_s > 50000:
            fs = max(200, int(50000 / duration_s))
        return fs

    def _read_sod(self):
        """Temps GPS courant (secondes-depuis-minuit) via le GNSS (None si absent /
        pas de fix). Sert à BORNER en temps-GPS chaque palier de fréquence pour
        corréler ensuite le `.dat` 250 Hz (horodaté GPS par le LC86G de l'unité)."""
        if self.gnss is None:
            return None
        try:
            self.gnss.read_fix(timeout=0.3)
            return self.gnss.utc_sod()
        except Exception:      # noqa: BLE001
            return None

    def correlate_dat_run(self, points, *, lsb_v: float, survey_path: str = "") -> dict:
        """Après un balayage STREAM AVEC enregistrement `.dat` (`start_unit=True`) :
        récupère les `.dat` (LS/GET) et **RE-mesure la sensibilité par voie à 250 Hz**
        — timestamps GPS PRÉCIS de l'unité (pas le jitter du STREAM 50 Hz software).

        Par palier, utilise la fenêtre temps-GPS (`sod_start`/`sod_end` capturés dans
        `measure_point_stream`) et la vitesse table déjà mesurée (accéléro NI). Lock-in
        du `.dat` via `coherent_phasor_at_times` sur les vrais temps GPS.

        Retour : {channel_id: {freq_hz: {counts_peak, sens_counts_per_mps,
                 sens_v_per_mps, n}}}.
        """
        from collections import defaultdict

        self.retrieve_files(survey_path)   # LS + GET → self._pulled
        segs = defaultdict(list)
        for path in self._pulled:
            for c in dat_reader.read_dat(path):
                sod0 = (c.start_time_ns / 1e9) % 86400.0
                sods = sod0 + np.arange(len(c.data)) / c.sample_rate_hz
                segs[c.channel_id].append((np.asarray(c.data, dtype=np.float64), sods))

        out = {cid: {} for cid in segs}
        for p in points:
            if p.get("skipped"):
                continue
            f = p["freq_hz"]
            t0, t1 = p.get("sod_start"), p.get("sod_end")
            vel = p.get("table_velocity_mps")
            if t0 is None or t1 is None:
                continue
            if t1 < t0:
                t0, t1 = t1, t0
            for cid, seglist in segs.items():
                xs, ts = [], []
                for data, sods in seglist:
                    m = (sods >= t0) & (sods <= t1)
                    if m.any():
                        xs.append(data[m]); ts.append(sods[m])
                if not xs:
                    continue
                cp = abs(coherent_phasor_at_times(
                    np.concatenate(xs), np.concatenate(ts), f))
                good = vel is not None and np.isfinite(vel) and vel > 0
                out[cid][f] = {
                    "counts_peak": cp,
                    "n": int(sum(len(x) for x in xs)),
                    "sens_counts_per_mps": cp / vel if good else float("nan"),
                    "sens_v_per_mps": cp * lsb_v / vel if good else float("nan"),
                }
        return out

    def measure_point_stream(self, freq_hz: float, n_cycles: int = 10,
                             min_duration_s: float = 2.0,
                             max_duration_s: float = 30.0,
                             ref_channel: int | None = None,
                             excite: bool = True, stream: bool = True) -> dict:
        """Un point de fréquence en **voie STREAM** : excite le shaker (si `excite`),
        co-acquiert l'accéléro de réf. + le flux géophone 3 voies sur la MÊME
        fenêtre, puis lock-in à `freq_hz` → sensibilité par voie.

        `excite=False` : ne pilote pas le shaker (test de plomberie / plancher de
        bruit — les amplitudes ne sont alors que du bruit).

        Retour : dict {freq_hz, accel_g, table_velocity_mps, channels:{ch:{...}}, …}.
        Sensibilité par voie en counts/g ET counts/(m/s) (un géophone = capteur de
        vitesse : `v = a/(2πf)`).
        """
        exc = None
        if excite:
            exc = self.bench.set_frequency_safe(freq_hz)
            if exc.get("skipped"):
                return {"freq_hz": freq_hz, "skipped": True,
                        "note": exc.get("note", ""), "channels": {}}

        # Fenêtre : au moins n_cycles, bornée [min,max] (en BF on allonge).
        duration = max(min_duration_s,
                       min(n_cycles / freq_hz if freq_hz > 0 else min_duration_s,
                           max_duration_s))
        accel_fs = self._accel_fs_for(freq_hz, duration)
        ref_idx = self.bench._ref_channel if ref_channel is None else ref_channel

        # Co-acquisition : accéléro dans un thread, flux géophone dans le principal,
        # démarrés ~ensemble → même fenêtre d'excitation. join() garanti (sinon
        # tâche NI orpheline → DAQmx -200557 aux points suivants).
        holder: dict = {}

        def _acq_accel():
            try:
                arr = self.bench._accel.acquire_seconds(duration, sample_rate=accel_fs)
                holder["ref"] = arr[ref_idx] if getattr(arr, "ndim", 1) == 2 else arr
            except Exception as e:   # noqa: BLE001
                holder["err"] = e

        sod_start = self._read_sod()   # borne temps-GPS (pour corréler le .dat 250 Hz)
        th = threading.Thread(target=_acq_accel, daemon=True)
        th.start()
        try:
            if stream:
                geo_fs, chans = self.unit.stream_geo(duration, rate_hz=50)
            else:
                # Chemin .dat : PAS de STREAM (il gêne l'enregistrement SD → recording
                # corrompu). On laisse juste le palier durer pendant que l'unité
                # enregistre son .dat, l'accéléro mesure la référence en parallèle.
                time.sleep(duration)
                geo_fs, chans = 50.0, {}
        finally:
            th.join()
        sod_end = self._read_sod()
        if "err" in holder:
            raise holder["err"]
        ref = np.asarray(holder["ref"], dtype=np.float64)

        # Lock-in accéléro → accélération table (g) et vitesse table (m/s).
        sens_v_per_g = self.bench._accel.sensitivity_v_per_g
        accel_g = coherent_amplitude_peak(ref, freq_hz, accel_fs) / sens_v_per_g
        vel_mps = (accel_g * G_ACCEL) / (2.0 * np.pi * freq_hz) if freq_hz > 0 else float("nan")

        # Lock-in par voie géophone → amplitude crête (counts) + phase + sensibilité.
        channels: dict = {}
        for ch, a in chans.items():
            ph = coherent_phasor(a, freq_hz, geo_fs)
            counts_peak = float(abs(ph))
            channels[ch] = {
                "counts_peak": counts_peak,
                "phase_rad": float(np.angle(ph)),
                "sens_counts_per_g": counts_peak / accel_g if accel_g > 0 else float("nan"),
                "sens_counts_per_mps": counts_peak / vel_mps if vel_mps and vel_mps > 0 else float("nan"),
                "snr_db": snr_db(a, freq_hz, geo_fs),
                "n": int(len(a)),
            }

        return {
            "freq_hz": freq_hz,
            "skipped": False,
            "accel_g": accel_g,
            "table_velocity_mps": vel_mps,
            "sod_start": sod_start,
            "sod_end": sod_end,
            "vpp": exc.get("vpp") if exc else None,
            "servo_measured_g": exc.get("measured_g") if exc else None,
            "accel_fs": accel_fs,
            "geo_fs": geo_fs,
            "accel_snr_db": snr_db(ref, freq_hz, accel_fs),
            "accel_thd_percent": thd_percent(ref, freq_hz, accel_fs),
            "channels": channels,
        }

    def run_stream(self, freqs, unit_config: dict | None = None,
                   start_unit: bool = False, excite: bool = True,
                   on_point=None, **point_kwargs) -> list[dict]:
        """Balayage en voie STREAM : (config unité) → pour chaque fréquence,
        `measure_point_stream` → liste de points. Coupe l'excitation à la fin.

        `start_unit=True` déclenche aussi l'enregistrement .dat de l'unité en
        parallèle (archive), mais la caractérisation se fait sur le STREAM.
        """
        if unit_config is not None:
            self.prepare_unit(unit_config)
        # Sécurité : vérifier l'accéléro AVANT toute excitation (anti-emballement).
        if excite:
            self.bench.check_reference_alive()
        if start_unit:
            self.start_unit()
        points: list[dict] = []
        # SÉCURITÉ : à l'excitation, balayer de la HAUTE vers la BASSE fréquence.
        # Le déplacement croît en 1/f² ; si un défaut (accéléro qui ne capte pas,
        # ampli muet, ZER non centré) fait ramper le servo, il se manifeste d'abord
        # aux HAUTES fréquences (petit déplacement) et l'abandon stoppe le balayage
        # AVANT d'atteindre les basses fréquences (grand déplacement → butée).
        # incident 2026-08-11 : 2 Hz balayé en premier a projeté l'armature en butée.
        order = sorted(freqs, reverse=True) if excite else list(freqs)
        try:
            for f in order:
                # Respecte le bouton « Arrêter » du GUI (stop_event du bench) entre
                # les points ; l'excitation elle-même est déjà interruptible (servo).
                self.bench._check_stop()
                pt = self.measure_point_stream(f, excite=excite, **point_kwargs)
                points.append(pt)
                if on_point is not None:
                    on_point(pt)
        finally:
            if start_unit:
                self.stop_unit()
            if excite:
                try:
                    self.bench._safe_shutdown()
                except Exception:   # noqa: BLE001
                    pass
        return points

    # ---- 5 : récupérer les enregistrements de l'unité ------------------
    def retrieve_files(self, survey_path: str = "") -> list[str]:
        """LS + GET tous les .dat de l'unité vers data_dir (préfixés du serial)."""
        os.makedirs(self.data_dir, exist_ok=True)
        self._pulled = self.unit.pull_all(self.data_dir, survey_path)
        return self._pulled

    # ---- 6 : corrélation .dat <-> accéléro de référence ----------------
    def correlate(self, schedule, ref_signal, ref_sods, *,
                  sens_v_per_g, lsb_v, unit_channels=None) -> dict:
        """CORRÉLATION TEMPS-GPS COMPLÈTE — aligne les voies de l'unité (`.dat`,
        horodatées en temps GPS par le LC86G) avec l'accéléromètre de référence
        (échantillonné NI, daté en temps GPS via le 1PPS ProPak sur PFI0), sur la
        **base GPS commune**, puis lock-in par voie par fréquence → sensibilité
        ET phase.

        Les deux capteurs ont des horloges DIFFÉRENTES ; on ne peut pas aligner
        par indice d'échantillon. On date chaque échantillon en **temps GPS
        (secondes-depuis-minuit UTC)** et on projette sur `exp(-j2πf·t_gps)`
        (`coherent_phasor_at_times`) → les phases sont dans le même référentiel.

        Paramètres
        ----------
        schedule     : liste de dict {"freq_hz", "sod_start", "sod_end"} — fenêtre
                       temps-GPS de chaque palier de fréquence du balayage.
        ref_signal   : échantillons accéléro de référence (VOLTS).
        ref_sods     : temps GPS (sod) de chaque échantillon de `ref_signal`
                       (via `Pps1ppsMonitor` + `gnss.pps.sample_to_gps_sod`).
        sens_v_per_g : sensibilité chaîne accéléro (V/g).
        lsb_v        : volts par count de l'ADC unité (2,048/gain / 2³¹).
        unit_channels: liste de `Channel3Axis` (défaut : lues des `.dat` de
                       `self._pulled`). Plusieurs segments par voie tolérés.

        Retour : {channel_id: {freq_hz: {sens_counts_per_mps, sens_v_per_mps,
                 phase_deg, accel_g, table_velocity_mps, n_ref, n_unit}}}.
        """
        from collections import defaultdict

        if unit_channels is None:
            unit_channels = []
            for path in self._pulled:
                unit_channels.extend(dat_reader.read_dat(path))
        ref_signal = np.asarray(ref_signal, dtype=np.float64)
        ref_sods = np.asarray(ref_sods, dtype=np.float64)

        # Segments groupés par voie, chacun daté en temps GPS (sod). start_time_ns
        # = ns depuis l'époque Unix (UTC) → sod = (ns/1e9) modulo 86400 s.
        segs = defaultdict(list)   # channel_id -> [(data, sods)]
        for c in unit_channels:
            sod0 = (c.start_time_ns / 1e9) % 86400.0
            sods = sod0 + np.arange(len(c.data)) / c.sample_rate_hz
            segs[c.channel_id].append((np.asarray(c.data, dtype=np.float64), sods))

        results = {cid: {} for cid in segs}
        for seg in schedule:
            f = float(seg["freq_hz"])
            t0, t1 = float(seg["sod_start"]), float(seg["sod_end"])
            # Référence : phaseur → accélération table (g) → vitesse table (m/s).
            m = (ref_sods >= t0) & (ref_sods <= t1)
            ref_ph = coherent_phasor_at_times(ref_signal[m], ref_sods[m], f)
            accel_g = abs(ref_ph) / sens_v_per_g if sens_v_per_g else float("nan")
            vel = (accel_g * G_ACCEL) / (2.0 * np.pi * f) if f > 0 else float("nan")
            for cid, seglist in segs.items():
                xs, ts = [], []
                for data, sods in seglist:
                    mu = (sods >= t0) & (sods <= t1)
                    if mu.any():
                        xs.append(data[mu]); ts.append(sods[mu])
                if xs:
                    unit_ph = coherent_phasor_at_times(
                        np.concatenate(xs), np.concatenate(ts), f)
                    n_unit = int(sum(len(x) for x in xs))
                else:
                    unit_ph, n_unit = 0j, 0
                counts_pk = abs(unit_ph)
                dphi = (np.angle(unit_ph) - np.angle(ref_ph) + np.pi) % (2 * np.pi) - np.pi
                good = vel is not None and np.isfinite(vel) and vel > 0
                results[cid][f] = {
                    "sens_counts_per_mps": counts_pk / vel if good else float("nan"),
                    "sens_v_per_mps": counts_pk * lsb_v / vel if good else float("nan"),
                    "phase_deg": float(np.degrees(dphi)),
                    "accel_g": accel_g,
                    "table_velocity_mps": vel,
                    "n_ref": int(m.sum()),
                    "n_unit": n_unit,
                }
        return results

    # ---- enchaînement complet -----------------------------------------
    def run(self, unit_config: dict, freqs, survey_path: str = "", *,
            gain: int = 1, **exc_kwargs) -> dict:
        """CHEMIN .dat + GPS COMPLET (1→6) : configure l'unité → START (+SYNC) →
        excite le shaker en co-acquérant l'accéléro de réf. daté en temps GPS →
        STOP → récupère les `.dat` (LS/GET, débloqué par le fix firmware) →
        corrèle (alignement GPS + lock-in par voie → sensibilité + phase).

        `gain` = gain ADC de l'unité (conversion counts→V). `exc_kwargs` passés à
        `run_excitation` (dwell_s, ai_rate…). Nécessite le matériel complet câblé.
        """
        cfg = self.prepare_unit(unit_config)
        self.start_unit()
        try:
            acq = self.run_excitation(freqs, **exc_kwargs)
        finally:
            self.stop_unit()
        files = self.retrieve_files(survey_path)
        lsb_v = 2.048 / gain / (2 ** 31)
        corr = self.correlate(acq["schedule"], acq["ref_signal"], acq["ref_sods"],
                              sens_v_per_g=acq["sens_v_per_g"], lsb_v=lsb_v)
        return {"config": cfg, "files": files, "sensitivity": corr, "acq": acq}
