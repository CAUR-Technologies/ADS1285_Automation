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
                           snr_db, thd_percent, G_ACCEL)


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
    def run_excitation(self, freqs, **sweep_kwargs) -> dict:
        """Excite le shaker pendant que l'unité enregistre, en capturant
        l'accéléro de référence ET le 1PPS pour l'horodatage GPS.

        TODO(matériel) : aujourd'hui l'accéléro (`equipment/accelerometer`) fait
        des fenêtres FINIES par point de fréquence. Pour cette session il faut une
        **acquisition continue** de l'accéléro pendant tout le balayage, avec le
        `Pps1ppsMonitor` armé sur la même horloge (ai/SampleClock) — puis relever,
        pour chaque échantillon accéléro, son temps GPS via
        `equipment.gnss.pps.sample_to_gps_sod`. À implémenter quand le GNSS + le
        1PPS (PFI0) sont câblés et testables.

        Squelette de la logique visée :
            self.pps.start()                       # armer le compteur 1PPS
            # ... lancer une acquisition accéléro CONTINUE + le balayage shaker ...
            edges = self.pps.read_edges()          # indices AI des fronts 1PPS
            utc = self.gnss.read_fix()             # seconde UTC de référence
            self.pps.stop()
        """
        raise NotImplementedError(
            "run_excitation : acquisition accéléro continue + co-capture 1PPS à "
            "implémenter avec le matériel (GNSS + 1PPS sur PFI0). Voir docstring.")

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

    def measure_point_stream(self, freq_hz: float, n_cycles: int = 10,
                             min_duration_s: float = 2.0,
                             max_duration_s: float = 30.0,
                             ref_channel: int | None = None,
                             excite: bool = True) -> dict:
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

        th = threading.Thread(target=_acq_accel, daemon=True)
        th.start()
        try:
            geo_fs, chans = self.unit.stream_geo(duration, rate_hz=50)
        finally:
            th.join()
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
                   **point_kwargs) -> list[dict]:
        """Balayage en voie STREAM : (config unité) → pour chaque fréquence,
        `measure_point_stream` → liste de points. Coupe l'excitation à la fin.

        `start_unit=True` déclenche aussi l'enregistrement .dat de l'unité en
        parallèle (archive), mais la caractérisation se fait sur le STREAM.
        """
        if unit_config is not None:
            self.prepare_unit(unit_config)
        if start_unit:
            self.start_unit()
        points: list[dict] = []
        try:
            for f in freqs:
                points.append(self.measure_point_stream(f, excite=excite, **point_kwargs))
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
    def correlate(self, ref_accel_g, ref_sample_gps_ns) -> dict:
        """Corrèle les 3 voies de l'unité (.dat) avec l'accéléro de référence.

        ref_accel_g        : échantillons accéléro de référence (g).
        ref_sample_gps_ns  : temps GPS (ns Unix) de chaque échantillon accéléro
                             (issu du 1PPS + GPGGA, cf. gnss.pps).

        TODO(vrai .dat) : pour chaque .dat récupéré,
            channels = dat_reader.read_dat(path)      # 3 Channel3Axis (ns Unix)
            # aligner chaque voie sur ref via les temps GPS (ré-échantillonnage),
            # puis, par fréquence d'excitation, lock-in des deux signaux et
            # sensibilité S_v = counts_crête / a_table [counts/(m/s)] par voie.
        Renvoie un dict {channel_id: {freq: sensibilité}} (à définir).
        """
        results = {}
        for path in self._pulled:
            channels = dat_reader.read_dat(path)   # noqa: F841 (usage à venir)
            # TODO : alignement temps GPS + lock-in par fréquence par voie.
            raise NotImplementedError(
                "correlate : alignement GPS + lock-in par voie à implémenter "
                "sur un vrai .dat (parse OK via dat_reader).")
        return results

    # ---- enchaînement complet -----------------------------------------
    def run(self, unit_config: dict, freqs, survey_path: str = "",
            **sweep_kwargs) -> dict:
        """Enchaîne 1→6. (run_excitation/correlate lèvent NotImplementedError
        tant que le matériel n'est pas là — le squelette pose le flux.)"""
        cfg = self.prepare_unit(unit_config)
        self.start_unit()
        try:
            acq = self.run_excitation(freqs, **sweep_kwargs)
        finally:
            self.stop_unit()
        files = self.retrieve_files(survey_path)
        corr = self.correlate(acq["ref_accel_g"], acq["ref_sample_gps_ns"])
        return {"config": cfg, "files": files, "sensitivity": corr}
