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
)


class Accelerometer:
    """Acquiert les données des accéléromètres via NI USB-6221."""

    def __init__(
        self,
        device: str = NI_DEVICE_NAME,
        channels: str = NI_AI_CHANNELS,
        sample_rate: int = NI_SAMPLE_RATE,
        samples_per_channel: int = NI_SAMPLES_PER_CHANNEL,
    ):
        self._device = device
        self._channels = [ch.strip() for ch in channels.split(",")]
        self._sample_rate = sample_rate
        self._samples_per_channel = samples_per_channel
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
        self._task.start()
        data = self._task.read(
            number_of_samples_per_channel=self._samples_per_channel,
            timeout=10.0,
        )
        self._task.stop()
        return np.array(data)

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
