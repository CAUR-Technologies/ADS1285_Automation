"""
Tests unitaires de base pour chaque module équipement.
Ces tests vérifient la logique sans connexion matérielle réelle
(les appels DLL/série/DAQ sont moqués).
"""

import unittest
from unittest.mock import MagicMock, patch


class TestADS1285(unittest.TestCase):
    @patch("equipment.ads1285.ads1285.ctypes.WinDLL")
    @patch("equipment.ads1285.ads1285.ET.parse")
    def test_connect_loads_dll(self, mock_parse, mock_dll):
        mock_parse.return_value.getroot.return_value = []
        from equipment.ads1285 import ADS1285
        adc = ADS1285()
        adc.connect()
        mock_dll.assert_called_once()

    @patch("equipment.ads1285.ads1285.ctypes.WinDLL")
    @patch("equipment.ads1285.ads1285.ET.parse")
    def test_unknown_register_raises(self, mock_parse, mock_dll):
        mock_parse.return_value.getroot.return_value = []
        from equipment.ads1285 import ADS1285
        adc = ADS1285()
        adc.connect()
        with self.assertRaises(ValueError):
            adc.write_register("INVALID_REG", 0xFF)


class TestWavetek39A(unittest.TestCase):
    @patch("equipment.wavetek.wavetek.serial.Serial")
    def test_invalid_waveform_raises(self, mock_serial):
        from equipment.wavetek import Wavetek39A
        gen = Wavetek39A()
        gen._serial = mock_serial()
        gen._serial.is_open = True
        with self.assertRaises(ValueError):
            gen.set_waveform("sawtooth")

    @patch("equipment.wavetek.wavetek.serial.Serial")
    def test_set_frequency_sends_command(self, mock_serial):
        from equipment.wavetek import Wavetek39A
        gen = Wavetek39A()
        gen._serial = mock_serial()
        gen._serial.is_open = True
        gen._serial.read_all.return_value = b""
        gen.set_frequency(10.0)
        gen._serial.write.assert_called()


class TestAPSController(unittest.TestCase):
    @patch("equipment.aps.aps_controller.serial.Serial")
    def test_send_command_raises_when_not_connected(self, mock_serial):
        from equipment.aps import APSController
        ctrl = APSController()
        with self.assertRaises(RuntimeError):
            ctrl.send_command("POS?")


if __name__ == "__main__":
    unittest.main()
