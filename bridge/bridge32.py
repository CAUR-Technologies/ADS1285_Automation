"""
Bridge 32-bit pour tiPHIChar.dll (ADS1285 EVM).

Ce script doit être lancé avec un interpréteur Python 32-bit.
Il charge la DLL 32-bit et expose ses fonctions via un socket TCP local.
Le script principal (64-bit) communique avec lui via PHIBridgeClient.

Protocole : JSON-lines sur TCP localhost
  Requête  : {"id": 1, "cmd": "PHI_Initialize", "args": [], "kwargs": {}}
  Réponse  : {"id": 1, "result": <valeur>, "error": null}
             {"id": 1, "result": null, "error": "message d'erreur"}

Usage :
    C:\Python311-32\python.exe bridge32.py [--port 9500]
"""

import ctypes
import json
import os
import socket
import threading
import argparse
import sys
import traceback as _tb

# Fichier log visible depuis le processus 32-bit
_LOG = os.path.join(os.path.dirname(__file__), "bridge32.log")

def _log(*args):
    msg = " ".join(str(a) for a in args)
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except BaseException:
        pass

DLL_PATH    = r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll"
SHARED_PATH = r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library"
DEFAULT_PORT = 9500


# ---------------------------------------------------------------------------
# Chargement de la DLL
# ---------------------------------------------------------------------------

def load_dll() -> ctypes.WinDLL:
    os.add_dll_directory(os.path.dirname(DLL_PATH))
    os.add_dll_directory(SHARED_PATH)
    return ctypes.WinDLL(DLL_PATH)


# ---------------------------------------------------------------------------
# Wrappers des fonctions PHI
# Signatures confirmées par sondage ctypes.
# ---------------------------------------------------------------------------

class PHIInterface:
    """Encapsule les appels ctypes a tiPHIChar.dll."""

    def __init__(self, dll: ctypes.WinDLL):
        self._dll = dll
        self._handle = ctypes.c_int32(0)
        self._psm_ctx = ctypes.c_int32(0)
        self._psm_path_buf = None   # ctypes buffer for PSM directory path
        self._setup_prototypes()

    def _setup_prototypes(self):
        d = self._dll
        P = ctypes.POINTER(ctypes.c_int32)

        # int PHI_CheckforDevices(int* pCount)
        d.PHI_CheckforDevices.restype  = ctypes.c_int32
        d.PHI_CheckforDevices.argtypes = [P]

        # int GetSerialNumbers(int* pCount, char* buffer)
        d.GetSerialNumbers.restype  = ctypes.c_int32
        d.GetSerialNumbers.argtypes = [P, ctypes.c_char_p]

        # int PHI_Initialize(int deviceIndex, int* pHandle)
        d.PHI_Initialize.restype  = ctypes.c_int32
        d.PHI_Initialize.argtypes = [ctypes.c_int32, P]

        # int PHI_Close(int handle)
        d.PHI_Close.restype  = ctypes.c_int32
        d.PHI_Close.argtypes = [ctypes.c_int32]

        # int PHI_BoardReset(int handle)
        d.PHI_BoardReset.restype  = ctypes.c_int32
        d.PHI_BoardReset.argtypes = [ctypes.c_int32]

        # int PHI_ReadFPGARegister(int handle, int devAddr, int regAddr, int* pValue)
        # devAddr = Device_Addr du Register Map XML (0=ADS1285, 1=DAC1282)
        d.PHI_ReadFPGARegister.restype  = ctypes.c_int32
        d.PHI_ReadFPGARegister.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                           ctypes.c_int32, P]

        # int PHI_WriteFPGARegister(int handle, int devAddr, int regAddr, int value)
        d.PHI_WriteFPGARegister.restype  = ctypes.c_int32
        d.PHI_WriteFPGARegister.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                            ctypes.c_int32, ctypes.c_int32]

        # int PHI_StartFiniteCapture(int handle, int numSamples)
        d.PHI_StartFiniteCapture.restype  = ctypes.c_int32
        d.PHI_StartFiniteCapture.argtypes = [ctypes.c_int32, ctypes.c_int32]

        # int PHI_ReadARM_ADC_Data(int handle, int selector, int* pValue)
        # Confirme par desassemblage : ecrit selector (byte) au registre 0x4c,
        # PHI_Process(0x4c), lit 4 octets du reg 0x4c et les assemble en int32
        # big-endian dans *pValue. Lecture single-shot, sans PHI_GetEvents.
        d.PHI_ReadARM_ADC_Data.restype  = ctypes.c_int32
        d.PHI_ReadARM_ADC_Data.argtypes = [ctypes.c_int32, ctypes.c_int32, P]

        # int PHI_Enable_PipeOut(int handle, int endpointAddr, int enable)
        d.PHI_Enable_PipeOut.restype  = ctypes.c_int32
        d.PHI_Enable_PipeOut.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

        # int PHI_Read_PipeOut(int handle, int endpointAddr, int length, unsigned char* buffer)
        d.PHI_Read_PipeOut.restype  = ctypes.c_int32
        d.PHI_Read_PipeOut.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                       ctypes.c_int32, ctypes.c_char_p]

        # int PHI_GetSoftwareVersionInfo(int unk, char* buffer)  -- signature incertaine
        d.PHI_GetSoftwareVersionInfo.restype  = ctypes.c_int32
        d.PHI_GetSoftwareVersionInfo.argtypes = [ctypes.c_int32, ctypes.c_char_p]

        # int PHI_Write(int handle, int channel, int offset, int length, unsigned char* data)
        d.PHI_Write.restype  = ctypes.c_int32
        d.PHI_Write.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                 ctypes.c_int32, ctypes.c_char_p]

        # int PHI_Read(int handle, int channel, int offset, int length, unsigned char* data)
        d.PHI_Read.restype  = ctypes.c_int32
        d.PHI_Read.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                ctypes.c_int32, ctypes.c_char_p]

        # int PHI_Process(int handle, int cmd, int* pResult)
        d.PHI_Process.restype  = ctypes.c_int32
        d.PHI_Process.argtypes = [ctypes.c_int32, ctypes.c_int32, P]

        # int PHILoadFPGAByMappingFile(int handle, char* xmlPath, int arg3)
        # arg3=10 confirme par call_log[437]: args=[handle, xml_ptr, 10, ...]
        d.PHILoadFPGAByMappingFile.restype  = ctypes.c_int32
        d.PHILoadFPGAByMappingFile.argtypes = [ctypes.c_int32, ctypes.c_char_p,
                                               ctypes.c_int32]

        # int PHI_SetWireIn(int handle, int ep, int value, int mask)
        d.PHI_SetWireIn.restype  = ctypes.c_int32
        d.PHI_SetWireIn.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                    ctypes.c_int32, ctypes.c_int32]

        # int PHI_UpdateWireIn(int handle, int ep, int value, int mask)
        # TI PHI combine SetWireIn+UpdateWireIn en une seule fonction
        d.PHI_UpdateWireIn.restype  = ctypes.c_int32
        d.PHI_UpdateWireIn.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                       ctypes.c_int32, ctypes.c_int32]

        # int PHI_ReadWireIn(int handle, int ep, ...)
        d.PHI_ReadWireIn.restype  = ctypes.c_int32
        d.PHI_ReadWireIn.argtypes = [ctypes.c_int32, ctypes.c_int32, P]

        # int PHI_Play_PipeIn(int handle, int ep, int unk, int flag)
        # 4 args confirme par call_log[511]: args[1:4]=[0, 0, 1] → ep=0, unk=0, flag=1
        # IMPORTANT: stdcall — passer exactement 4 args sinon corruption de pile
        d.PHI_Play_PipeIn.restype  = ctypes.c_int32
        d.PHI_Play_PipeIn.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                      ctypes.c_int32, ctypes.c_int32]

        # int PHI_ClosePSM(int handle, int psm_id)
        d.PHI_ClosePSM.restype  = ctypes.c_int32
        d.PHI_ClosePSM.argtypes = [ctypes.c_int32, ctypes.c_int32]

        # int PHI_ARM_Firmware_Load(int handle, ...)
        d.PHI_ARM_Firmware_Load.restype  = ctypes.c_int32
        d.PHI_ARM_Firmware_Load.argtypes = [ctypes.c_int32]

        # int PHI_ReadWireOut(int handle, int ep, int* pValue)
        d.PHI_ReadWireOut.restype  = ctypes.c_int32
        d.PHI_ReadWireOut.argtypes = [ctypes.c_int32, ctypes.c_int32, P]

        # int PHI_InitializePSM(int handle, int psm_id, char* psm_dir_path)
        # psm_dir_path : chemin ASCII vers le repertoire contenant DataMem.bin et CMdMem.bin.
        # La DLL copie ce chemin dans un buffer heap et stocke le pointeur a handle+0x90.
        # Ce pointeur est ensuite passe comme arg3 a PHI_LoadPSM.
        d.PHI_InitializePSM.restype  = ctypes.c_int32
        d.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                         ctypes.c_char_p]

        # int PHI_Load_PipeIn(int handle, int ep, unsigned char* data, int length)
        d.PHI_Load_PipeIn.restype  = ctypes.c_int32
        d.PHI_Load_PipeIn.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                      ctypes.c_char_p, ctypes.c_int32]

        # int PHI_LoadPSM(int handle, int psm_id, int ctxHandle, int arg4)
        # ctxHandle = pointeur heap vers le chemin PSM (stocke a handle+0x90 par InitializePSM)
        # arg4      = 1 (valeur observee dans le call_log de la GUI)
        d.PHI_LoadPSM.restype  = ctypes.c_int32
        d.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                   ctypes.c_int32, ctypes.c_int32]

        # int PHI_RunPSM(int handle, int psm_id, int num_samples)
        d.PHI_RunPSM.restype  = ctypes.c_int32
        d.PHI_RunPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

        # int PHI_AbortPSM(int handle)
        d.PHI_AbortPSM.restype  = ctypes.c_int32
        d.PHI_AbortPSM.argtypes = [ctypes.c_int32]

        # int PHI_SetClockRate(int handle, int type, int unk, float* rate_ptr)
        # Le 4e arg est un pointeur vers float (adresse stack dans la GUI).
        # 0x41700000 = 15.0f = taux de base de l'horloge.
        d.PHI_SetClockRate.restype  = ctypes.c_int32
        d.PHI_SetClockRate.argtypes = [ctypes.c_int32, ctypes.c_int32,
                                       ctypes.c_int32,
                                       ctypes.POINTER(ctypes.c_float)]

        # int PHI_FPGAReset(int handle)
        d.PHI_FPGAReset.restype  = ctypes.c_int32
        d.PHI_FPGAReset.argtypes = [ctypes.c_int32]

        # int PHI_ARMReset(int handle)
        d.PHI_ARMReset.restype  = ctypes.c_int32
        d.PHI_ARMReset.argtypes = [ctypes.c_int32]

        # int PHI_OverrideDefaults(int handle, int mode)
        d.PHI_OverrideDefaults.restype  = ctypes.c_int32
        d.PHI_OverrideDefaults.argtypes = [ctypes.c_int32, ctypes.c_int32]

    # --- Commandes exposees au client 64-bit ---

    def check_devices(self) -> int:
        count = ctypes.c_int32(0)
        self._dll.PHI_CheckforDevices(ctypes.byref(count))
        return count.value

    def get_serial_numbers(self) -> str:
        count = ctypes.c_int32(0)
        buf = ctypes.create_string_buffer(256)
        self._dll.GetSerialNumbers(ctypes.byref(count), buf)
        return buf.value.decode(errors="replace")

    def get_version(self) -> str:
        buf = ctypes.create_string_buffer(256)
        self._dll.PHI_GetSoftwareVersionInfo(ctypes.c_int32(0), buf)
        return buf.value.decode(errors="replace")

    def initialize(self, device_index=0) -> int:
        ret = self._dll.PHI_Initialize(device_index, ctypes.byref(self._handle))
        return ret

    def close(self) -> int:
        ret = self._dll.PHI_Close(self._handle)
        self._handle = ctypes.c_int32(0)
        return ret

    def board_reset(self) -> int:
        return self._dll.PHI_BoardReset(self._handle)

    def fpga_reset(self) -> int:
        return self._dll.PHI_FPGAReset(self._handle)

    def override_defaults(self, mode=0) -> int:
        return self._dll.PHI_OverrideDefaults(self._handle, mode)

    def phi_write(self, channel, offset, data_bytes) -> int:
        length = len(data_bytes)
        buf = ctypes.create_string_buffer(bytes(data_bytes), length)
        return self._dll.PHI_Write(self._handle, channel, offset, length, buf)

    def phi_read(self, channel, offset, length) -> dict:
        buf = ctypes.create_string_buffer(length)
        ret = self._dll.PHI_Read(self._handle, channel, offset, length, buf)
        return {"ret": ret, "data": list(buf.raw)}

    def phi_process(self, cmd) -> dict:
        result = ctypes.c_int32(0)
        ret = self._dll.PHI_Process(self._handle, cmd, ctypes.byref(result))
        return {"ret": ret, "result": result.value}

    def _initialize_with_retry(self, timeout=30.0) -> int:
        """
        Tente PHI_Initialize(0) avec retries jusqu'a `timeout` secondes.
        Ferme le handle invalide entre les essais et attend le device USB.
        Retourne le code de retour du dernier essai.
        """
        import time
        t_deadline = time.time() + timeout
        attempt = 0
        ret = -1
        while time.time() < t_deadline:
            attempt += 1
            ret = self.initialize(0)
            _log(f"    _init_retry essai {attempt}: ret={ret}  handle={self._handle.value}")
            if ret == 0:
                break
            # Fermer le handle invalide
            if self._handle.value != 0:
                self._dll.PHI_Close(self._handle)
                self._handle = ctypes.c_int32(0)
            # Attendre que le device soit accessible (poll + pause)
            import time as _t
            count = ctypes.c_int32(0)
            t_poll = _t.time() + 3.0
            while _t.time() < t_poll:
                self._dll.PHI_CheckforDevices(ctypes.byref(count))
                if count.value > 0:
                    break
                _t.sleep(0.2)
            _t.sleep(1.0)  # stabilisation supplementaire avant prochain essai
        _log(f"    _init_retry: {attempt} essai(s), ret final={ret}  "
             f"handle={self._handle.value}")
        return ret

    def load_fpga_by_mapping_file(self, xml_path, arg3=10) -> int:
        return self._dll.PHILoadFPGAByMappingFile(
            self._handle, xml_path.encode("mbcs"), ctypes.c_int32(arg3)
        )

    def set_wire_in(self, ep, value, mask=0xFFFFFFFF) -> int:
        return self._dll.PHI_SetWireIn(self._handle, ep, value, mask)

    def update_wire_in(self, ep, value, mask=0xFFFF) -> int:
        """PHI_UpdateWireIn est un combo SetWire+Update (4 args dans TI PHI)."""
        return self._dll.PHI_UpdateWireIn(self._handle, ep, value, mask)

    def play_pipe_in(self, ep=0, unk=0, flag=1) -> int:
        # flag=1 confirme par call_log[511]: args[1:4]=[ep=0, unk=0, flag=1]
        return self._dll.PHI_Play_PipeIn(self._handle, ep,
                                         ctypes.c_int32(unk), ctypes.c_int32(flag))

    def close_psm(self, psm_id: int = 0) -> int:
        return self._dll.PHI_ClosePSM(self._handle, ctypes.c_int32(psm_id))

    def arm_firmware_load(self) -> int:
        return self._dll.PHI_ARM_Firmware_Load(self._handle)

    def read_wire_out(self, ep) -> dict:
        value = ctypes.c_int32(0)
        ret = self._dll.PHI_ReadWireOut(self._handle, ep, ctypes.byref(value))
        return {"ret": ret, "value": value.value}

    def initialize_psm(self, psm_id: int = 0, psm_dir: str = "") -> int:
        # arg3 = chemin ASCII vers le repertoire contenant DataMem.bin et CMdMem.bin.
        # La DLL copie ce chemin en heap et stocke le pointeur a handle+0x90.
        # Ce pointeur (ctx) est ensuite passe a PHI_LoadPSM comme 3e argument.
        # Confirme par analyse assembleur de PHI_InitializePSM et du call_log GUI.
        if psm_dir:
            path_buf = ctypes.create_string_buffer(psm_dir.encode("mbcs") + b"\x00")
        else:
            # Fallback : buffer vide (chemin vide — PHI_LoadPSM echouera sur fopen)
            path_buf = ctypes.create_string_buffer(512)
        _log(f"  PHI_InitializePSM({psm_id}, dir={psm_dir!r})")
        ret = self._dll.PHI_InitializePSM(
            self._handle, ctypes.c_int32(psm_id), path_buf
        )
        # La DLL alloue un bloc heap (200 octets) a handle+0x90, mais fn_C
        # copie le chemin dans le slot inline handle+0x94 — le bloc heap
        # reste VIDE.  PHI_LoadPSM attend un pointeur vers la chaine chemin
        # comme arg3 (sprintf "%s\\DataMem.bin").
        # Solution : on alloue notre propre buffer ctypes avec le chemin et
        # on passe son adresse a PHI_LoadPSM, contournant le heap DLL casse.
        if psm_dir:
            self._psm_path_buf = ctypes.create_string_buffer(
                psm_dir.encode("mbcs") + b"\x00", 512
            )
            _log(f"  psm_path_buf allocated at 0x{ctypes.addressof(self._psm_path_buf):08X}")
        _log(f"  PHI_InitializePSM -> {ret}")
        return ret

    def load_pipe_in(self, ep, data_bytes) -> int:
        length = len(data_bytes)
        buf = ctypes.create_string_buffer(bytes(data_bytes), length)
        return self._dll.PHI_Load_PipeIn(self._handle, ep, buf, length)

    def load_psm(self, psm_id) -> int:
        # Utiliser notre propre buffer chemin (fiable) plutot que le heap DLL (vide).
        if self._psm_path_buf is not None:
            ctx = ctypes.addressof(self._psm_path_buf)
        else:
            # Fallback : heap DLL a handle+0x90
            ctx = ctypes.c_int32.from_address(self._handle.value + 0x90).value
        _log(f"  PHI_LoadPSM({psm_id}, ctx=0x{ctx:08X}, arg4=1)")
        # Diagnostic : lire le chemin pointe par ctx
        if ctx:
            try:
                raw = (ctypes.c_byte * 256).from_address(ctx)
                end = bytes(raw).find(b'\x00')
                path_str = bytes(raw)[:end].decode('mbcs', errors='replace') if end >= 0 else '?'
                _log(f"  ctx path = {path_str!r}")
            except Exception as _e:
                _log(f"  ctx path: lecture impossible ({_e})")
        # arg4=1 : valeur confirmee par le call_log de la GUI TI
        return self._dll.PHI_LoadPSM(self._handle, psm_id, ctx, ctypes.c_int32(1))

    def run_psm(self, psm_id, num_samples=1) -> int:
        return self._dll.PHI_RunPSM(self._handle, psm_id, num_samples)

    def _load_psm_pipe(self, data_bytes: bytes) -> None:
        """Charge un script PSM via la sequence Load_PipeIn + Play_PipeIn."""
        n = len(data_bytes)
        n_le = list(n.to_bytes(4, 'little'))
        self.phi_write(1, 12288, n_le)
        self.phi_write(1, 2304, [1, 0, 0, 0])
        self.phi_process(2304)
        self.load_pipe_in(0, list(data_bytes))
        self.phi_write(1, 16388, [0])
        self.phi_write(1, 16384, [1, 0, 0, 0])
        self.phi_write(1, 2308, [1, 0, 0, 0])
        self.phi_process(2308)
        self.play_pipe_in(0)

    def acquire_samples(self, num_samples: int,
                        psm_acq_path: str, psm_seq_path: str,
                        sample_rate: int = 4000) -> dict:
        """
        Acquiert num_samples echantillons 32-bit via le mecanisme PSM.

        Sequence capturee par spy_phi_dll.py (call_log idx 729-791).
        sample_rate : taux d'echantillonnage en Hz (4000, 2000, 1000, 500, 250).

        IMPORTANT endianness : les octets retournes sont little-endian (natif FPGA/x86).
        Interprete-les avec struct.unpack_from('<i', ...) ou int.from_bytes(..., 'little').
        """
        import time, struct

        with open(psm_acq_path, "rb") as f:
            psm_acq = f.read()
        with open(psm_seq_path, "rb") as f:
            psm_seq = f.read()

        n_bytes = num_samples * 4  # 4 octets par echantillon

        # 0. Selectionner le canal analogique (wire 5, valeur 0, masque 0x1F).
        #    Confirme par call_log idx 721 : PHI_UpdateWireIn(5, 0, 31) avant chaque
        #    acquisition dans le GUI TI. Sans cet appel, le mux est potentiellement
        #    dans un etat indefini et on lit du bruit au lieu du signal capteur.
        self.update_wire_in(5, 0, 0x1F)
        _log("  acquire: UpdateWireIn(5, 0, 0x1F) — selection canal capteur")

        # 1. Initialiser le moteur PSM
        # Le repertoire psm0/ (au meme niveau que psm_acq_path) contient
        # DataMem.bin (= psm_04_40B.bin) et CMdMem.bin (= psm_05_200B.bin)
        # utilises par PHI_LoadPSM pour configurer le PSM.
        _psm_dir = os.path.join(os.path.dirname(os.path.abspath(psm_acq_path)), "psm0")
        self.initialize_psm(0, psm_dir=_psm_dir)

        # 2. Configuration wires
        self.update_wire_in(20, 1, 0xFFFF)
        self.update_wire_in(21, 1, 0xFFFF)
        self.update_wire_in(3, 1, 0x000F)

        # 3. Charger PSM d'acquisition (ex. psm_04_40B)
        self._load_psm_pipe(psm_acq)
        self.update_wire_in(3, 2, 0x000F)

        # 4. Charger PSM de sequencement (ex. psm_05_200B)
        self._load_psm_pipe(psm_seq)
        self.update_wire_in(3, 19, 0x001F)
        self.update_wire_in(3,  0, 0x0010)

        # 5. LoadPSM (utilise le ctx handle de InitializePSM) + config buffer
        ret = self.load_psm(0)
        _log(f"  acquire: PHI_LoadPSM -> {ret}")
        n_bytes_le = list(n_bytes.to_bytes(4, 'little'))
        self.phi_write(1, 4096, n_bytes_le)
        self.phi_write(1, 2048, [1, 0, 0, 0])
        self.phi_process(2048)

        # 6. Activer PipeOut et lancer
        self.enable_pipe_out(0, n_bytes)
        self.update_wire_in(20, 2, 0xFFFF)
        self.run_psm(0, num_samples)

        # 7. Attendre la fin de l'acquisition en pollant le compteur d'octets
        #    disponibles : registre (channel 1, offset 4108). Confirme par
        #    spy_getevents.py : passe de 0 a n_bytes quand les donnees sont pretes.
        wait_s = num_samples / float(sample_rate) + 0.5
        deadline = time.time() + wait_s + 5.0
        avail = 0
        polls = 0
        while time.time() < deadline:
            buf4 = ctypes.create_string_buffer(4)
            self._dll.PHI_Read(self._handle, 1, 4108, 4, buf4)
            avail = int.from_bytes(buf4.raw, "little")
            polls += 1
            if avail >= n_bytes:
                break
            time.sleep(0.02)
        _log(f"  acquire: poll reg4108 -> {avail} octets dispo (cible {n_bytes}, {polls} lectures)")

        # 8. Trigger lecture et lire les donnees
        self.phi_write(1, 56,   [0, 0, 0, 0])
        self.phi_write(1, 2060, [1, 0, 0, 0])
        self.phi_process(2060)
        result = self.phi_read(3, 9216, n_bytes)

        # 9. Diagnostic endianness : logguer les 2 premiers echantillons
        #    interpretes en big-endian et en little-endian pour comparer
        #    avec la valeur de reference PHI_ReadARM_ADC_Data (~1868 au repos).
        raw = result["data"]
        if len(raw) >= 8:
            be0 = struct.unpack_from(">i", bytes(raw[0:4]))[0]
            le0 = struct.unpack_from("<i", bytes(raw[0:4]))[0]
            be1 = struct.unpack_from(">i", bytes(raw[4:8]))[0]
            le1 = struct.unpack_from("<i", bytes(raw[4:8]))[0]
            _log(f"  acquire: ech[0] BE={be0:12d}  LE={le0:12d}")
            _log(f"  acquire: ech[1] BE={be1:12d}  LE={le1:12d}")
            _log(f"  acquire: bytes[0:8] = {raw[:8]}")

        # 10. Fermer le PSM (peut crasher si PHI_LoadPSM n'a pas ete appele)
        try:
            self.close_psm(0)
        except OSError as e:
            _log(f"  acquire: PHI_ClosePSM echoue (attendu): {e}")

        nz = sum(1 for b in result["data"] if b != 0)
        _log(f"  acquire: {len(result['data'])} octets lus (rc={result['ret']}), non_zero={nz}")
        return result

    def abort_psm(self) -> int:
        return self._dll.PHI_AbortPSM(self._handle)

    def set_clock_rate(self, rate_type=0, unk=0, rate_float=15.0) -> int:
        rate_buf = ctypes.c_float(rate_float)
        return self._dll.PHI_SetClockRate(
            self._handle,
            ctypes.c_int32(rate_type),
            ctypes.c_int32(unk),
            ctypes.byref(rate_buf),
        )

    def initialize_full(self, fpga_bin_path, psm_bin_paths,
                        xml_map_path, call_log_path=None) -> dict:
        """
        Rejoue la sequence d'initialisation complete.
        Tous les fichiers sont lus localement par le bridge 32-bit.
        On ne passe que des chemins (pas de donnees volumineuses via TCP).
        """
        _log(f"initialize_full: fpga={fpga_bin_path}")
        _log(f"  psm={psm_bin_paths}")
        _log(f"  xml={xml_map_path}")
        _log(f"  log={call_log_path}")

        # Lire le call_log depuis le disque
        call_log = None
        if call_log_path and os.path.isfile(call_log_path):
            with open(call_log_path, encoding="utf-8") as fh:
                call_log = json.load(fh)
            _log(f"  call_log charge: {len(call_log)} entrees")
        else:
            raise RuntimeError(f"call_log introuvable : {call_log_path!r}")

        # Lire le bitfile FPGA
        with open(fpga_bin_path, "rb") as fh:
            fpga_data = fh.read()
        _log(f"  FPGA binaire: {len(fpga_data)}B")

        results = {}

        # Fin d'init = juste avant le premier PHI_GetEvents/PHI_GetEVMDetails
        init_end = next(
            (i for i, c in enumerate(call_log)
             if c["fn"] in ("PHI_GetEvents", "PHI_GetEVMDetails")),
            len(call_log)
        )

        psm_bin_iter = iter(psm_bin_paths)
        fpga_chunks  = 0
        handle_valid = False   # True apres le premier PHI_Initialize reussi

        for idx, c in enumerate(call_log[:init_end]):
            fn  = c["fn"]
            a   = c["args"]   # a[0]=handle (ignore), a[1..4]=params utiles
            buf = c.get("buf")
            _log(f"  replay [{idx:3d}] {fn}  args[1:4]={a[1:4]}")

            # --- Appels sans handle (toujours surs) ---
            if fn == "PHI_CheckforDevices":
                count = ctypes.c_int32(0)
                self._dll.PHI_CheckforDevices(ctypes.byref(count))
                continue

            if fn == "PHI_Close":
                # PHI_Close [17] est le premier appel du cycle reset ARM.
                # Dans la GUI TI ce Close met le handle en etat "ferme" et
                # PHI_ARMReset fonctionne (ret=0). Pour un handle fresh (cold-start)
                # ce Close donne FE-9 sur ARMReset.
                # STRATEGY ALTERNATIVE : on saute ce Close et on garde le handle
                # OUVERT pour PHI_ARMReset. Avec le handle ouvert, ARMReset retourne
                # USB-5 MAIS le hardware ARM se remet physiquement a zero (bootloader).
                # On fera le Close + Re-Initialize APRES ARMReset pour rafraichir
                # la connexion USB stale (voir handler PHI_ARMReset ci-dessous).
                _log(f"  PHI_Close SAUTE (strategie: ARMReset avec handle ouvert + "
                     f"Close/ReInit post-reset)")
                continue

            if fn == "PHI_Initialize":
                # Retry avec close/wait: le device peut etre en cours de boot
                # ou la connexion USB stale (USB-13) apres un test precedent.
                ret = self._initialize_with_retry(timeout=30.0)
                # handle valide SEULEMENT si retour = 0 ET handle non nul
                handle_valid = (ret == 0 and self._handle.value != 0)
                results[f"initialize_{idx}"] = ret
                _log(f"  PHI_Initialize -> {ret}  handle={self._handle.value}  "
                     f"valid={handle_valid}")
                continue

            # --- Ignorer tout ce qui suit si le handle n'est pas encore valide ---
            # (les premiers appels du call_log utilisaient un handle pre-existant
            #  de la session GUI precedente — inutilisable pour un cold start)
            if not handle_valid:
                continue

            if fn == "PHI_OverrideDefaults":
                self.override_defaults(a[1])

            elif fn == "PHI_Write":
                ch, addr, ln = a[1], a[2], a[3]
                if ch == 6:
                    # Charger depuis le fichier binaire plutot que le buf JSON
                    chunk = fpga_data[addr: addr + ln]
                    if chunk:
                        ret = self.phi_write(6, addr, chunk)
                        fpga_chunks += 1
                        if fpga_chunks == 1:
                            _log(f"  FPGA: chargement de {len(fpga_data)}B en cours... (ret premier bloc={ret})")
                        elif fpga_chunks % 100 == 0:
                            _log(f"  FPGA: {fpga_chunks} blocs (ret={ret})")
                        if ret != 0 and fpga_chunks <= 3:
                            _log(f"  FPGA: ERREUR bloc {fpga_chunks} addr={addr} ret={ret}")
                elif buf:
                    ret = self.phi_write(ch, addr, buf)
                    if ret != 0:
                        _log(f"  PHI_Write(ch={ch}, addr={addr}, ln={ln}) -> {ret}")

            elif fn == "PHI_Process":
                r = self.phi_process(a[1])
                if r["ret"] != 0:
                    _log(f"  PHI_Process({a[1]}) -> ret={r['ret']} result={r['result']}")

            elif fn == "PHI_ARMReset":
                # On appelle PHI_ARMReset avec le handle OUVERT (non ferme).
                # Avec handle ouvert: ret=USB-5 — cela provoque un reset USB complet
                # (ARM + FPGA/USB re-enumeration). Le device disparait et revient.
                # Strategie: Close + polling CheckforDevices + Re-Initialize quand
                # le device USB est revenu (avec timeout 30s).
                ret = self._dll.PHI_ARMReset(self._handle)
                _log(f"  PHI_ARMReset (handle ouvert) -> {ret}")
                import time
                time.sleep(0.5)  # laisser le reset USB se propager
                # Fermer le handle stale
                ret_close = self._dll.PHI_Close(self._handle)
                _log(f"  PHI_Close post-ARMReset -> {ret_close}")
                self._handle = ctypes.c_int32(0)
                # Attendre la re-enumeration USB (jusqu'a 30s)
                count = ctypes.c_int32(0)
                deadline = time.time() + 30.0
                while time.time() < deadline:
                    time.sleep(0.5)
                    self._dll.PHI_CheckforDevices(ctypes.byref(count))
                    if count.value > 0:
                        _log(f"  Device USB revenu apres {30.0-(deadline-time.time()):.1f}s")
                        break
                else:
                    _log("  TIMEOUT: device USB pas revenu apres 30s")
                # Re-Initialiser avec le device maintenant present (avec retries)
                time.sleep(0.5)  # stabilisation initiale
                ret2 = self._initialize_with_retry(timeout=30.0)
                _log(f"  Re-PHI_Initialize post-ARMReset -> {ret2}  "
                     f"handle={self._handle.value}")
                handle_valid = (ret2 == 0 and self._handle.value != 0)

            elif fn == "PHI_ARM_Firmware_Load":
                # args[0]=0 = device_index (PAS le handle) d'apres le call_log.
                # Apres cet appel, l'ARM reboot avec le nouveau firmware.
                # FE-13 ("Communication lost") est ATTENDU : l'ARM reboote et
                # le USB peut re-enumerer. Il faut attendre le retour du device
                # avant la prochaine PHI_Initialize (call_log index [419]).
                # On NE re-initialise PAS ici — on laisse la replay le faire
                # quand elle arrive a [419] (PHI_Initialize dans le call_log).
                device_idx = ctypes.c_int32(a[0])
                ret = self._dll.PHI_ARM_Firmware_Load(device_idx)
                _log(f"  PHI_ARM_Firmware_Load(device={a[0]}) -> {ret}")
                import time
                time.sleep(0.5)
                # Fermer le handle stale (ARM reboote avec nouveau firmware)
                ret_close = self._dll.PHI_Close(self._handle)
                _log(f"  PHI_Close post-FirmwareLoad -> {ret_close}")
                self._handle = ctypes.c_int32(0)
                handle_valid = False  # invalidate handle — [419] PHI_Initialize le recreera
                # Attendre la re-enumeration USB apres ARM reboot (jusqu'a 30s)
                count = ctypes.c_int32(0)
                deadline = time.time() + 30.0
                while time.time() < deadline:
                    time.sleep(0.5)
                    self._dll.PHI_CheckforDevices(ctypes.byref(count))
                    if count.value > 0:
                        elapsed = 30.0 - (deadline - time.time())
                        _log(f"  Device USB revenu apres ARM reboot ({elapsed:.1f}s)")
                        break
                else:
                    _log("  TIMEOUT: device pas revenu apres PHI_ARM_Firmware_Load (30s)")
                # [419] PHI_Initialize dans le call_log aura aussi un retry loop
                # via le handler PHI_Initialize ci-dessus. Pas besoin de re-init ici.

            elif fn == "PHILoadFPGA":
                # PHILoadFPGA(handle, buf_ptr, size=464307)
                #
                # Toujours appeler PHILoadFPGA pour charger PHI_generic.bit.
                # Raison : le FPGA charge son flash d'usine (bitfile ancien) apres
                # une reconnexion USB.  Sans le bon bitfile, PHI_UpdateWireIn
                # retourne 8192 au lieu de 0 et les commandes ADC echouent.
                #
                # ATTENTION : si le FPGA tourne deja (handle_valid), PHILoadFPGA
                # reprogramme le FPGA → reset de l'interface OpalKelly USB → USB-13
                # sur les ops ARM suivantes.  Apres chargement, on teste si l'ARM
                # repond encore.  Si non → Close + attente + ReInit.
                #
                # Chercher le bitfile dans l'ordre de priorite :
                #   1. Bitfile capture par spy_getevents2.py (tools/getevents_buffers/)
                #   2. Bitfile installe par la GUI TI (ProgramData)
                import glob as _glob
                _prog_data_bit = (
                    r"C:\ProgramData\Texas Instruments\ADS1285\Bit Files\PHI_generic.bit"
                )
                fpga_bitfile_candidates = _glob.glob(
                    os.path.join(os.path.dirname(os.path.dirname(fpga_bin_path)),
                                 "tools", "getevents_buffers", "fpga_bitfile_*.bin")
                )
                # Priorite : capture spy > ProgramData
                fpga_bit_path = None
                if fpga_bitfile_candidates:
                    fpga_bit_path = sorted(fpga_bitfile_candidates)[-1]
                elif os.path.isfile(_prog_data_bit):
                    fpga_bit_path = _prog_data_bit

                if fpga_bit_path:
                    with open(fpga_bit_path, "rb") as _fh:
                        fpga_bit_data = _fh.read()
                    _log(f"  PHILoadFPGA: bitfile {fpga_bit_path} ({len(fpga_bit_data)}B)")
                    # int PHILoadFPGA(int handle, unsigned char* buf, int size)
                    _buf = ctypes.create_string_buffer(fpga_bit_data, len(fpga_bit_data))
                    try:
                        self._dll.PHILoadFPGA.restype  = ctypes.c_int32
                        self._dll.PHILoadFPGA.argtypes = [
                            ctypes.c_int32, ctypes.c_char_p, ctypes.c_int32
                        ]
                        ret = self._dll.PHILoadFPGA(self._handle, _buf,
                                                     ctypes.c_int32(len(fpga_bit_data)))
                        results["fpga_load"] = ret
                        _log(f"  PHILoadFPGA({len(fpga_bit_data)}B) -> {ret}")

                        if ret == 0:
                            # Tester immediatement si l'ARM repond (ch=1, addr=514).
                            # Si USB reset a eu lieu (FPGA deja charge), ret_test=13.
                            # Si FPGA etait vide (premiere prog), ret_test=0.
                            import time as _ti
                            _arm_test_buf = ctypes.create_string_buffer(4)
                            self._dll.PHI_Read.restype  = ctypes.c_int32
                            self._dll.PHI_Read.argtypes = [ctypes.c_int32,
                                ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                ctypes.c_char_p]
                            ret_test = self._dll.PHI_Read(self._handle,
                                ctypes.c_int32(1), ctypes.c_int32(514),
                                ctypes.c_int32(1), _arm_test_buf)
                            _log(f"  PHILoadFPGA: test ARM (read ch=1 addr=514) -> {ret_test}")
                            if ret_test != 0:
                                # USB reset detecte — Close + attente + ReInit
                                _log("  PHILoadFPGA: USB reset detecte — Close+ReInit...")
                                _ti.sleep(2.0)   # laisser le FPGA demarrer
                                try:
                                    self._dll.PHI_Close(self._handle)
                                except Exception:
                                    pass
                                self._handle = ctypes.c_int32(0)
                                _ti.sleep(2.0)   # stabilisation USB
                                ret2 = self._initialize_with_retry(timeout=30.0)
                                _log(f"  ReInit post-PHILoadFPGA -> ret={ret2} "
                                     f"handle={self._handle.value}")
                                if ret2 != 0:
                                    _log("  AVERTISSEMENT: ReInit post-PHILoadFPGA"
                                         f" echoue (ret={ret2}) — USB-13 probable")
                            else:
                                _log("  PHILoadFPGA: ARM repond — pas de Close+ReInit")
                    except Exception as _e:
                        _log(f"  PHILoadFPGA: exception {_e}")
                else:
                    _log(f"  PHILoadFPGA SAUTE: bitfile FPGA non trouve. "
                         f"Capturer avec tools/spy_getevents2.py.")

            elif fn == "PHILoadFPGAByMappingFile":
                # "PHILoadFPGAByMappingFile" attend le Mapping.ini (ProgramData).
                # Mapping.ini: [ads1285evm] FirmwareFileName = PHI_generic.bit
                # → la DLL lit le device name, charge PHI_generic.bit depuis le meme
                #   repertoire, configure le FPGA.
                _mapping_ini = (
                    r"C:\ProgramData\Texas Instruments\ADS1285\Bit Files\Mapping.ini"
                )
                arg3 = a[2] if len(a) > 2 else 10
                # Utiliser Mapping.ini en priorite, fallback sur xml_map_path
                _map_path = _mapping_ini if os.path.isfile(_mapping_ini) else xml_map_path
                ret = self.load_fpga_by_mapping_file(_map_path, arg3)
                results["fpga_mapping"] = ret
                _log(f"  PHILoadFPGAByMappingFile(path={_map_path!r}, arg3={arg3}) -> {ret}")

            elif fn == "PHI_UpdateWireIn":
                ret = self.update_wire_in(a[1], a[2], a[3])
                if ret != 0:
                    _log(f"  PHI_UpdateWireIn(ep={a[1]}, val={a[2]}, mask={a[3]}) -> {ret}")

            elif fn == "PHI_SetClockRate":
                # Signature inconnue — args[3] est probablement un pointeur stack
                # de la GUI (adresse invalide dans notre processus).
                # On journalise et on continue sans appeler la DLL.
                _log(f"  PHI_SetClockRate SAUTE (signature a clarifier, args={a[1:4]})")

            elif fn == "PHI_InitializePSM":
                psm_id_init = a[1] if len(a) > 1 else 0
                # Utiliser le 1er fichier PSM pour deriver le repertoire psm0/
                first_psm = psm_bin_paths[0] if psm_bin_paths else ""
                _psm_dir = os.path.join(os.path.dirname(os.path.abspath(first_psm)), "psm0") if first_psm else ""
                ret = self.initialize_psm(psm_id_init, psm_dir=_psm_dir)
                _log(f"  PHI_InitializePSM({psm_id_init}, dir={_psm_dir!r}) -> {ret}")

            elif fn == "PHI_Load_PipeIn":
                ep = a[1]
                psm_path = next(psm_bin_iter, None)
                if psm_path:
                    with open(psm_path, "rb") as fh:
                        psm_data = fh.read()
                    ret = self.load_pipe_in(ep, psm_data)
                    _log(f"  PHI_Load_PipeIn ep=0x{ep:02X} {len(psm_data)}B -> {ret}")
                else:
                    _log("  AVERTISSEMENT: plus de fichiers PSM")

            elif fn == "PHI_Play_PipeIn":
                ret = self.play_pipe_in(a[1])
                _log(f"  PHI_Play_PipeIn(ep={a[1]}) -> {ret}")

            elif fn == "PHI_LoadPSM":
                ret = self.load_psm(a[1])
                _log(f"  PHI_LoadPSM({a[1]}) -> {ret}")

            elif fn == "PHI_Enable_PipeOut":
                self.enable_pipe_out(a[1], a[2])

            elif fn == "PHI_RunPSM":
                ret = self.run_psm(a[1])
                _log(f"  PHI_RunPSM({a[1]}) -> {ret}")

            elif fn == "PHI_ClosePSM":
                psm_id = a[1] if len(a) > 1 else 0
                try:
                    ret = self.close_psm(psm_id)
                    _log(f"  PHI_ClosePSM({psm_id}) -> {ret}")
                except OSError as e:
                    _log(f"  PHI_ClosePSM({psm_id}) echoue: {e}")

            # PHI_Read, PHI_ReadWireIn, PHI_CheckforDevices supplementaires,
            # PHI_ReadEEPROMData, PHI_GetEVMEEPROMInfo, Read_Ini_Data,
            # PHILoadFPGA, PHILoadFPGA_File : lectures/status — ignores

        results["fpga_chunks"] = fpga_chunks
        _log(f"  FPGA: {fpga_chunks} blocs charges au total")
        _log("  Initialisation complete.")
        return results

    def read_register(self, dev_addr, reg_addr) -> dict:
        """
        dev_addr : Device_Addr du Register Map (0=ADS1285, 1=DAC1282)
        reg_addr : adresse du registre
        """
        value = ctypes.c_int32(0)
        ret = self._dll.PHI_ReadFPGARegister(
            self._handle, dev_addr, reg_addr, ctypes.byref(value)
        )
        return {"ret": ret, "value": value.value}

    def write_register(self, dev_addr, reg_addr, value) -> int:
        return self._dll.PHI_WriteFPGARegister(self._handle, dev_addr, reg_addr, value)

    def start_finite_capture(self, num_samples) -> int:
        return self._dll.PHI_StartFiniteCapture(self._handle, num_samples)

    def read_arm_adc_data(self, selector=0) -> dict:
        """Lit un echantillon ADC 32-bit via PHI_ReadARM_ADC_Data (single-shot)."""
        val = ctypes.c_int32(0)
        ret = self._dll.PHI_ReadARM_ADC_Data(self._handle, selector, ctypes.byref(val))
        return {"ret": ret, "value": val.value}

    def acquire_arm(self, num_samples, selector=0, delay_us=0) -> dict:
        """Boucle de lecture single-shot cote bridge (rapide, sans aller-retour socket).

        Retourne {"ret": <dernier rc>, "data": [int32, ...]}.
        delay_us : pause optionnelle entre lectures (microsecondes).
        """
        import time
        samples = []
        val = ctypes.c_int32(0)
        last_ret = 0
        for _ in range(num_samples):
            last_ret = self._dll.PHI_ReadARM_ADC_Data(self._handle, selector,
                                                      ctypes.byref(val))
            samples.append(val.value)
            if delay_us:
                time.sleep(delay_us / 1_000_000.0)
        nz = sum(1 for s in samples if s != 0)
        _log(f"  acquire_arm: {len(samples)} samples (sel={selector}), non_zero={nz}, "
             f"min={min(samples) if samples else 0}, max={max(samples) if samples else 0}")
        return {"ret": last_ret, "data": samples}

    def enable_pipe_out(self, endpoint, enable=1) -> int:
        return self._dll.PHI_Enable_PipeOut(self._handle, endpoint, enable)

    def read_pipe_out(self, endpoint, length) -> dict:
        buf = ctypes.create_string_buffer(length)
        ret = self._dll.PHI_Read_PipeOut(self._handle, endpoint, length, buf)
        return {"ret": ret, "data": list(buf.raw)}

    def dispatch(self, cmd, args, kwargs):
        """Aiguille une commande recue du client vers la bonne methode."""
        methods = {
            "check_devices":           lambda: self.check_devices(),
            "get_serial_numbers":      lambda: self.get_serial_numbers(),
            "get_version":             lambda: self.get_version(),
            "initialize":              lambda: self.initialize(*args, **kwargs),
            "close":                   lambda: self.close(),
            "board_reset":             lambda: self.board_reset(),
            "fpga_reset":              lambda: self.fpga_reset(),
            "read_register":           lambda: self.read_register(*args, **kwargs),
            "write_register":          lambda: self.write_register(*args, **kwargs),
            "phi_write":               lambda: self.phi_write(*args, **kwargs),
            "phi_read":                lambda: self.phi_read(*args, **kwargs),
            "phi_process":             lambda: self.phi_process(*args, **kwargs),
            "load_fpga_by_mapping":    lambda: self.load_fpga_by_mapping_file(*args, **kwargs),
            "set_wire_in":             lambda: self.set_wire_in(*args, **kwargs),
            "update_wire_in":          lambda: self.update_wire_in(*args, **kwargs),
            "read_wire_out":           lambda: self.read_wire_out(*args, **kwargs),
            "initialize_psm":          lambda: self.initialize_psm(*args, **kwargs),
            "load_pipe_in":            lambda: self.load_pipe_in(*args, **kwargs),
            "load_psm":                lambda: self.load_psm(*args, **kwargs),
            "run_psm":                 lambda: self.run_psm(*args, **kwargs),
            "abort_psm":               lambda: self.abort_psm(),
            "play_pipe_in":            lambda: self.play_pipe_in(*args, **kwargs),
            "close_psm":               lambda: self.close_psm(),
            "arm_firmware_load":       lambda: self.arm_firmware_load(),
            "set_clock_rate":          lambda: self.set_clock_rate(*args, **kwargs),
            "initialize_full":         lambda: self.initialize_full(
                                           args[0], args[1], args[2],
                                           args[3] if len(args) > 3 else None),
            "start_finite_capture":    lambda: self.start_finite_capture(*args, **kwargs),
            "read_arm_adc_data":       lambda: self.read_arm_adc_data(*args, **kwargs),
            "acquire_arm":             lambda: self.acquire_arm(*args, **kwargs),
            "enable_pipe_out":         lambda: self.enable_pipe_out(*args, **kwargs),
            "read_pipe_out":           lambda: self.read_pipe_out(*args, **kwargs),
            "acquire_samples":         lambda: self.acquire_samples(
                                           args[0], args[1], args[2],
                                           args[3] if len(args) > 3 else 4000),
        }
        if cmd not in methods:
            raise ValueError("Commande inconnue : " + cmd)
        return methods[cmd]()


# ---------------------------------------------------------------------------
# Serveur TCP
# ---------------------------------------------------------------------------

class _Shutdown(Exception):
    """Signal interne pour arreter le serveur proprement."""

def handle_client(conn, phi):
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    req = json.loads(line.decode())
                    if req.get("cmd") == "shutdown":
                        resp = {"id": req.get("id"), "result": "ok", "error": None}
                        conn.sendall((json.dumps(resp) + "\n").encode())
                        raise _Shutdown
                    result = phi.dispatch(req["cmd"], req.get("args", []), req.get("kwargs", {}))
                    resp = {"id": req.get("id"), "result": result, "error": None}
                except _Shutdown:
                    raise
                except Exception as e:
                    tb = _tb.format_exc()
                    _log("ERROR:", tb)
                    resp = {"id": req.get("id"), "result": None, "error": tb}
                conn.sendall((json.dumps(resp) + "\n").encode())
    except _Shutdown:
        _log("Shutdown demande par le client.")
        # Fermer proprement la connexion USB avant de quitter.
        # os._exit() bypasse les destructeurs — sans ce close, la prochaine
        # instance du bridge trouve le device USB en etat 'deja ouvert' -> USB-13.
        try:
            if phi._handle.value != 0:
                ret_c = phi._dll.PHI_Close(phi._handle)
                phi._handle = ctypes.c_int32(0)
                _log(f"  PHI_Close on shutdown -> {ret_c}")
        except Exception as _exc:
            _log(f"  PHI_Close on shutdown ERREUR: {_exc}")
        os._exit(0)
    finally:
        conn.close()


def run_server(port):
    # Reinitialiser le log
    open(_LOG, "w").close()
    dll = load_dll()
    phi = PHIInterface(dll)
    startup_msg = "[bridge32] DLL chargee. Ecoute sur localhost:" + str(port)
    _log(startup_msg)
    # Envoyer le message de demarrage au parent via stdout (lu une seule fois).
    # Apres cela, stdout n'est plus utilise — _log ecrit uniquement dans le fichier.
    print(startup_msg, flush=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, phi), daemon=True)
        t.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bridge 32-bit pour tiPHIChar.dll")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    run_server(args.port)
