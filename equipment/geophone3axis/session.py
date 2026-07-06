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
import time

from equipment.geophone3axis.geophone3axis import Geophone3Axis
from equipment.geophone3axis import dat_reader


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
