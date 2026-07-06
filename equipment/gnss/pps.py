"""
Capture du 1PPS GNSS alignée sur l'acquisition analogique NI (carte USB-6221).

Objectif : donner à CHAQUE échantillon de l'accéléromètre de référence un temps
GPS absolu, pour corréler les mesures du banc avec les .dat GPS-datés de l'unité
3 axes.

Technique NI (corrélation événement ↔ acquisition, standard) : un COMPTEUR compte
les tops de l'horloge d'échantillonnage analogique (`/Dev/ai/SampleClock`) et est
**latché à chaque front montant du 1PPS** (câblé sur **PFI0**, utilisé comme
sample clock du compteur). Chaque valeur lue = le **nombre d'échantillons AI**
acquis à l'instant de ce front 1PPS → l'INDICE d'échantillon de chaque frontière
de seconde GPS. Combiné à l'heure UTC du GPGGA (quelle seconde), on obtient le
temps GPS de n'importe quel échantillon :

    t_gps(n) = seconde_UTC(front k) + (n - S_k) / f_ech       (S_k = indice du front k)

⚠️ Nécessite que la tâche AI (accéléromètre) tourne (elle génère `ai/SampleClock`).
La tâche compteur doit donc être démarrée pendant que l'AI acquiert (intégration
en Phase 3). Sur la USB-6221 les lignes port0 sont software-timed → on passe par
le compteur + PFI0 (matériel), pas par une DIO échantillonnée.
"""

import nidaqmx
from nidaqmx.constants import Edge, AcquisitionType, READ_ALL_AVAILABLE


class Pps1ppsMonitor:
    """Capture les fronts 1PPS (PFI) en indices d'échantillon de l'horloge AI."""

    def __init__(self, device: str = "Dev1", pfi_terminal: str = "PFI0",
                 counter: str = "ctr0"):
        self._device = device
        self._pfi = pfi_terminal
        self._counter = counter
        self._task: nidaqmx.Task | None = None

    def start(self, max_pps: int = 4000) -> None:
        """Arme la capture. À appeler pendant que la tâche AI tourne
        (ai/SampleClock actif). `max_pps` = profondeur du buffer (fronts)."""
        self._task = nidaqmx.Task()
        ch = self._task.ci_channels.add_ci_count_edges_chan(
            f"{self._device}/{self._counter}", edge=Edge.RISING)
        # Le compteur compte les tops de l'horloge d'échantillonnage analogique.
        ch.ci_count_edges_term = f"/{self._device}/ai/SampleClock"
        # ... et il est échantillonné (latché) à chaque front montant du 1PPS.
        self._task.timing.cfg_samp_clk_timing(
            rate=2.0,   # nominal (1PPS ≈ 1 Hz) ; la source réelle est le PFI
            source=f"/{self._device}/{self._pfi}",
            active_edge=Edge.RISING,
            sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=max_pps,
        )
        self._task.start()

    def read_edges(self) -> list[int]:
        """Indices d'échantillon AI de chaque front 1PPS capturé depuis le dernier
        appel (liste éventuellement vide si aucun 1PPS depuis)."""
        if self._task is None:
            return []
        data = self._task.read(number_of_samples_per_channel=READ_ALL_AVAILABLE)
        if data is None:
            return []
        return [int(x) for x in data] if isinstance(data, list) else [int(data)]

    def stop(self) -> None:
        if self._task is not None:
            try:
                self._task.stop()
            except Exception:      # noqa: BLE001
                pass
            try:
                self._task.close()
            except Exception:      # noqa: BLE001
                pass
            self._task = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()


def pps_period_s(edge_sample_indices, ai_rate_hz: float) -> list[float]:
    """Périodes (s) entre fronts 1PPS successifs, à partir de leurs indices
    d'échantillon AI et du taux AI. Devrait valoir ≈ 1,000 s (santé GNSS/jitter)."""
    idx = sorted(int(i) for i in edge_sample_indices)
    return [(b - a) / float(ai_rate_hz) for a, b in zip(idx, idx[1:])]


def sample_to_gps_sod(sample_index: int, edge_sample_indices, edge_utc_sods,
                      ai_rate_hz: float) -> float | None:
    """Temps GPS (secondes-depuis-minuit UTC) d'un échantillon AI donné.

    edge_sample_indices : indices d'échantillon des fronts 1PPS (Pps1ppsMonitor).
    edge_utc_sods       : seconde UTC entière associée à chaque front (via GPGGA).
    Utilise le front 1PPS le plus proche + l'interpolation par le taux AI.
    """
    if not edge_sample_indices or not edge_utc_sods:
        return None
    pairs = sorted(zip((int(i) for i in edge_sample_indices), edge_utc_sods))
    # front le plus proche (en indice) de sample_index
    best_s, best_sod = min(pairs, key=lambda p: abs(p[0] - sample_index))
    return best_sod + (sample_index - best_s) / float(ai_rate_hz)
