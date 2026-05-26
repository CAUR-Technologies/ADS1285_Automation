"""
Module Accéléromètre — NI USB-6221 + interface Spektra
Acquisition via nidaqmx.
"""

import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration
from config.settings import (
    NI_DEVICE_NAME,
    NI_AI_CHANNELS,
    NI_SAMPLE_RATE,
    NI_SAMPLES_PER_CHANNEL,
    ACCEL_SENSITIVITY_V_PER_G,
)
from equipment.dsp import coherent_amplitude_peak, snr_db, thd_percent, rms


class Accelerometer:
    """Acquiert les données des accéléromètres via NI USB-6221.

    Canal de référence = accéléromètre MEMS Silicon Designs 2240-005 (800 mV/g)
    via boîte de conversion Spektra. La sensibilité de la chaîne complète est
    donnée par sensitivity_v_per_g (ajuster si la boîte applique un gain).
    """

    def __init__(
        self,
        device: str = NI_DEVICE_NAME,
        channels: str = NI_AI_CHANNELS,
        sample_rate: int = NI_SAMPLE_RATE,
        samples_per_channel: int = NI_SAMPLES_PER_CHANNEL,
        sensitivity_v_per_g: float = ACCEL_SENSITIVITY_V_PER_G,
        ref_channel: int = 0,
    ):
        self._device = device
        self._channels = [ch.strip() for ch in channels.split(",")]
        self._sample_rate = sample_rate
        self._samples_per_channel = samples_per_channel
        self._sensitivity = sensitivity_v_per_g
        self._ref_channel = ref_channel
        self._task: nidaqmx.Task | None = None

    def connect(self) -> None:
        """Crée et configure la tâche NI-DAQmx."""
        self._task = nidaqmx.Task()
        for ch in self._channels:
            self._task.ai_channels.add_ai_voltage_chan(
                f"{self._device}/{ch}",
                terminal_config=TerminalConfiguration.RSE,
                min_val=-10.0,
                max_val=10.0,
            )
        self._task.timing.cfg_samp_clk_timing(
            rate=self._sample_rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=self._samples_per_channel,
        )
        print(f"Accéléromètre connecté : {self._device}, canaux {self._channels}.")

    def disconnect(self) -> None:
        """Ferme et libère la tâche NI-DAQmx."""
        if self._task:
            self._task.close()
            self._task = None
        print("Accéléromètre déconnecté.")

    def acquire(self) -> np.ndarray:
        """
        Lance une acquisition finie et retourne un tableau numpy.
        Forme : (num_channels, samples_per_channel)
        """
        if not self._task:
            raise RuntimeError("Accéléromètre non connecté.")
        return self._acquire_window(self._sample_rate, self._samples_per_channel)

    # ─────────────────────────────────────────────────────────────────────
    # Mesure d'amplitude par détection cohérente (lock-in mono-bin)
    # ─────────────────────────────────────────────────────────────────────

    def _acquire_window(self, sample_rate: int, samples: int) -> np.ndarray:
        """
        Acquisition finie avec timing reconfiguré à la volée.

        Restaure le timing par défaut après lecture pour ne pas perturber
        les appels acquire() ultérieurs.
        """
        if not self._task:
            raise RuntimeError("Accéléromètre non connecté.")
        self._task.timing.cfg_samp_clk_timing(
            rate=sample_rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=samples,
        )
        self._task.start()
        timeout = samples / sample_rate + 5.0
        data = self._task.read(number_of_samples_per_channel=samples,
                               timeout=timeout)
        self._task.stop()
        # Restaurer le timing par défaut
        self._task.timing.cfg_samp_clk_timing(
            rate=self._sample_rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=self._samples_per_channel,
        )
        return np.array(data)

    def _ref_idx(self, ref_channel):
        return self._ref_channel if ref_channel is None else ref_channel

    def measure_acceleration_g(self,
                               freq_hz: float,
                               n_cycles: int = 5,
                               max_duration_s: float = 20.0,
                               as_rms: bool = False,
                               ref_channel: int | None = None) -> float:
        """
        Mesure l'amplitude d'accélération (g) à la fréquence d'excitation par
        détection cohérente (DFT mono-bin à freq_hz).

        Indispensable en basse fréquence où le signal (ex. 1,2 mV à 0,0015 g)
        est noyé dans le bruit : la détection cohérente rejette tout ce qui
        n'est pas à freq_hz.

        Parameters
        ----------
        freq_hz : fréquence d'excitation (Hz)
        n_cycles : nombre de cycles à acquérir (fenêtre = n_cycles / freq)
        max_duration_s : durée d'acquisition maximale (borne le cas basse fréq.)
        as_rms : si True retourne l'amplitude RMS, sinon l'amplitude crête
        ref_channel : index du canal de référence (défaut : self._ref_channel)

        Returns
        -------
        Accélération (g), crête par défaut.
        """
        ref, fs = self.acquire_reference(freq_hz, n_cycles, max_duration_s,
                                         ref_channel)
        amp_peak_v = coherent_amplitude_peak(ref, freq_hz, fs)
        volts = amp_peak_v / np.sqrt(2.0) if as_rms else amp_peak_v
        return volts / self._sensitivity

    def acquire_reference(self, freq_hz: float,
                          n_cycles: int = 5,
                          max_duration_s: float = 20.0,
                          ref_channel: int | None = None):
        """
        Acquiert une fenêtre du canal de référence adaptée à freq_hz.

        ref_channel : index du canal (un accéléromètre de référence par axe ;
        défaut : self._ref_channel).

        Returns (signal_np, fs) — permet de calculer plusieurs métriques
        (g, SNR, THD) à partir d'une seule acquisition.
        """
        if freq_hz <= 0:
            raise ValueError("freq_hz doit être > 0")
        # Fenêtre couvrant n_cycles, bornée pour éviter des acquisitions
        # interminables en très basse fréquence ; ≥ 50 éch./cycle.
        duration = min(n_cycles / freq_hz, max_duration_s)
        fs = int(min(max(freq_hz * 50.0, 200.0), 5000.0))
        samples = max(int(fs * duration), 64)
        data = self._acquire_window(fs, samples)
        idx = self._ref_idx(ref_channel)
        ref = data[idx] if data.ndim == 2 else data
        return np.asarray(ref, dtype=np.float64), fs

    def measure(self, freq_hz: float,
                n_cycles: int = 5,
                max_duration_s: float = 20.0,
                ref_channel: int | None = None) -> dict:
        """
        Mesure complète à freq_hz en une acquisition : accélération (g),
        SNR (dB) et THD (%). ref_channel sélectionne l'accéléromètre de l'axe.
        """
        ref, fs = self.acquire_reference(freq_hz, n_cycles, max_duration_s,
                                         ref_channel)
        amp_peak_v = coherent_amplitude_peak(ref, freq_hz, fs)
        return {
            "accel_g": amp_peak_v / self._sensitivity,
            "snr_db": snr_db(ref, freq_hz, fs),
            "thd_percent": thd_percent(ref, freq_hz, fs),
            "fs": fs,
        }

    def measure_noise_floor(self, duration_s: float = 5.0,
                            ref_channel: int | None = None) -> float:
        """
        Plancher de bruit : RMS du canal de référence (g), shaker arrêté.
        """
        fs = self._sample_rate
        samples = max(int(fs * duration_s), 64)
        data = self._acquire_window(fs, samples)
        idx = self._ref_idx(ref_channel)
        ref = data[idx] if data.ndim == 2 else data
        return rms(ref) / self._sensitivity

    @property
    def sensitivity_v_per_g(self) -> float:
        return self._sensitivity

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def num_channels(self) -> int:
        return len(self._channels)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
