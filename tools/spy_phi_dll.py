"""
Spy sur les appels a tiPHIChar.dll pendant que la GUI TI tourne.

Usage :
  1. Lancer la GUI TI : ADS1285 EVM.exe
  2. Dans un autre terminal (venv 64-bit) :
       venv\Scripts\python.exe tools\spy_phi_dll.py
  3. Connecter l'EVM dans la GUI
  4. Lire quelques registres dans la GUI
  5. Ctrl+C pour arreter — la sequence complete s'affiche
"""

import frida
import sys
import json
import time

DLL_NAME = "tiPHIChar.dll"

# Fonctions a surveiller (toutes les exports connues)
FUNCTIONS = [
    "GetSerialNumbers",
    "PHILoadFPGA",
    "PHILoadFPGAByMappingFile",
    "PHILoadFPGA_File",
    "PHI_ARMReset",
    "PHI_ARM_Firmware_Load",
    "PHI_AbortPSM",
    "PHI_BoardReset",
    "PHI_BufferReinitialise",
    "PHI_CheckforDevices",
    "PHI_ClearEEPROM",
    "PHI_ClearWireIn",
    "PHI_Close",
    "PHI_CloseAll",
    "PHI_ClosePSM",
    "PHI_EEPROMLoader",
    "PHI_EEPROMWriteProtect",
    "PHI_Enable_PipeOut",
    "PHI_FPGAReset",
    "PHI_GetDVDDStatus",
    "PHI_GetEVMDetails",
    "PHI_GetEVMEEPROMInfo",
    "PHI_GetErrorInfo",
    "PHI_GetEvents",
    "PHI_GetFirmwareVersionInfo",
    "PHI_GetPLLMN_Values",
    "PHI_GetPSMScriptStatus",
    "PHI_GetPowerSupplyStates",
    "PHI_GetSoftwareVersionInfo",
    "PHI_GetStatus_PipeIn",
    "PHI_GetStatus_PipeOut",
    "PHI_I2CRWCustom",
    "PHI_Init_S",
    "PHI_Initialize",
    "PHI_InitializePSM",
    "PHI_LoadPSM",
    "PHI_LoadPSM_DAC",
    "PHI_Load_PipeIn",
    "PHI_ModeSet_PipeOut",
    "PHI_OverrideDefaults",
    "PHI_Play_PipeIn",
    "PHI_Process",
    "PHI_Read",
    "PHI_ReadARM_ADC_Data",
    "PHI_ReadEEPROMData",
    "PHI_ReadFPGARegister",
    "PHI_ReadWireIn",
    "PHI_ReadWireOut",
    "PHI_Read_PipeOut",
    "PHI_RunPSM",
    "PHI_SPI1_RWCustom",
    "PHI_SelectPLLClockInput",
    "PHI_SetClockRate",
    "PHI_SetDVDDControl",
    "PHI_SetPLLValues",
    "PHI_SetPowerSupplyStates",
    "PHI_SetWireIn",
    "PHI_StartCapture",
    "PHI_StartFiniteCapture",
    "PHI_ToggleWireIn",
    "PHI_UpdateWireIn",
    "PHI_Write",
    "PHI_WriteFPGARegister",
    "PHI_WriteWireIn",
    "Read_Ini_Data",
    "RuntimeLogEnable",
]

hook_calls = "\n        ".join([f'hookFn(mod, "{f}");' for f in FUNCTIONS])

js_code = (
    "(function() {\n"
    "    var dll = '" + DLL_NAME + "';\n"
    "    var hooksInstalled = false;\n"
    "\n"
    "    function readBuf(ptr, len) {\n"
    "        try {\n"
    "            if (ptr.isNull()) return null;\n"
    "            var bytes = [];\n"
    "            for (var i = 0; i < len && i < 4096; i++)\n"
    "                bytes.push(ptr.add(i).readU8());\n"
    "            return bytes;\n"
    "        } catch(e) { return null; }\n"
    "    }\n"
    "\n"
    "    function hookFn(mod, name) {\n"
    "        try {\n"
    "            var addr = mod.findExportByName(name);\n"
    "            if (!addr) return;\n"
    "            Interceptor.attach(addr, {\n"
    "                onEnter: function(args) {\n"
    "                    this.fnName = name;\n"
    "                    this.a0 = args[0].toInt32();\n"
    "                    this.a1 = args[1].toInt32();\n"
    "                    this.a2 = args[2].toInt32();\n"
    "                    this.a3 = args[3].toInt32();\n"
    "                    this.a4 = args[4].toInt32();\n"
    "                    this.buf = null;\n"
    "                    // PHI_Write(h, channel, offset, length, data_ptr)\n"
    "                    if (name === 'PHI_Write') {\n"
    "                        var ch = this.a1;\n"
    "                        var ln = this.a3;\n"
    "                        // channel 6 = FPGA bitfile (can be large)\n"
    "                        // channel 0/1/2 = register writes (keep if <= 64 bytes)\n"
    "                        if (ch === 6 || (ch <= 2 && ln <= 64)) {\n"
    "                            this.buf = readBuf(args[4], ln);\n"
    "                        }\n"
    "                    }\n"
    "                    // PHI_Load_PipeIn(h, pipe, data_ptr, length)\n"
    "                    if (name === 'PHI_Load_PipeIn') {\n"
    "                        this.buf = readBuf(args[2], this.a3);\n"
    "                    }\n"
    "                    // PHI_LoadPSM / PHI_InitializePSM — capturer arg2\n"
    "                    if (name === 'PHI_LoadPSM' || name === 'PHI_InitializePSM') {\n"
    "                        this.buf = readBuf(args[2], 64);\n"
    "                    }\n"
    "                },\n"
    "                onLeave: function(retval) {\n"
    "                    var bufAfter = null;\n"
    "                    if (this.fnName === 'PHI_InitializePSM') {\n"
    "                        bufAfter = readBuf(ptr(this.a2), 64);\n"
    "                    }\n"
    "                    send({\n"
    "                        type: 'call',\n"
    "                        fn: this.fnName,\n"
    "                        args: [this.a0, this.a1, this.a2, this.a3, this.a4],\n"
    "                        buf: this.buf,\n"
    "                        bufAfter: bufAfter,\n"
    "                        ret: retval.toInt32()\n"
    "                    });\n"
    "                }\n"
    "            });\n"
    "        } catch(e) {}\n"
    "    }\n"
    "\n"
    "    function installHooks() {\n"
    "        if (hooksInstalled) return;\n"
    "        var mod = Process.findModuleByName(dll);\n"
    "        if (!mod) return;\n"
    "        hooksInstalled = true;\n"
    "        send({type:'info', msg:'DLL trouvee a ' + mod.base + ' - hooks actifs'});\n"
    "        " + hook_calls + "\n"
    "    }\n"
    "\n"
    "    // Essai immediat si DLL deja chargee\n"
    "    installHooks();\n"
    "\n"
    "    // Fallback : sondage toutes les 300 ms jusqu'a ce que la DLL soit chargee\n"
    "    setInterval(function() {\n"
    "        if (!hooksInstalled) installHooks();\n"
    "    }, 300);\n"
    "\n"
    "})();\n"
)

call_log = []

def on_message(message, data):
    if message["type"] == "send":
        payload = message["payload"]
        if payload["type"] == "call":
            call_log.append(payload)
            extra = ""
            if payload.get("buf"):
                extra += f"  [buf:{len(payload['buf'])}B]"
            if payload.get("bufAfter"):
                extra += f"  [bufAfter:{payload['bufAfter'][:32]}]"
            print(f"  {payload['fn']:35s}  args={payload['args']}  ret={payload['ret']}{extra}")
        elif payload["type"] == "info":
            print(f"[INFO] {payload['msg']}")
        elif payload["type"] == "error":
            print(f"[ERREUR] {payload['msg']}")
    elif message["type"] == "error":
        print(f"[FRIDA ERREUR] {message['stack']}")


def find_target_pid():
    device = frida.get_local_device()
    for proc in device.enumerate_processes():
        if "ADS1285" in proc.name or "ads1285" in proc.name.lower():
            return proc.pid
    return None


print("Attente de la GUI TI (ADS1285 EVM.exe)... Lancez-la maintenant.")
pid = None
while pid is None:
    pid = find_target_pid()
    if pid is None:
        time.sleep(0.5)

print(f"GUI trouvee (PID {pid}). Attachement Frida...")
session = frida.attach(pid)
script = session.create_script(js_code)
script.on("message", on_message)
script.load()

print(f"Surveillance active sur {DLL_NAME}.")
print("Connectez l'EVM dans la GUI, lisez quelques registres, puis Ctrl+C.\n")
print(f"{'Fonction':<35}  {'Args (4 premiers)':<30}  Ret")
print("-" * 80)

try:
    sys.stdin.read()
except KeyboardInterrupt:
    pass

import os
out_dir = os.path.join(os.path.dirname(__file__), "..", "bridge", "phi_binaries")
os.makedirs(out_dir, exist_ok=True)

print("\n\n=== SEQUENCE COMPLETE ===")
fpga_buf = bytearray()
psm_idx  = 0

for i, c in enumerate(call_log):
    buf = c.get("buf")
    extra = ""

    # Assembler le bitfile FPGA depuis les blocs PHI_Write channel=6
    if c["fn"] == "PHI_Write" and len(c["args"]) >= 2 and c["args"][1] == 6 and buf:
        fpga_buf.extend(bytes(buf))
        extra = f"  [FPGA +{len(buf)}B total={len(fpga_buf)}]"

    # Sauvegarder chaque buffer PHI_Load_PipeIn
    if c["fn"] == "PHI_Load_PipeIn" and buf:
        fname = os.path.join(out_dir, f"psm_{psm_idx:02d}_{len(buf)}B.bin")
        with open(fname, "wb") as f:
            f.write(bytes(buf))
        psm_idx += 1
        extra = f"  [SAUVEGARDE -> {fname}]"

    print(f"{i+1:3d}. {c['fn']:35s}  args={c['args']}  ret={c['ret']}{extra}")

# Sauvegarder le call log complet en JSON (sans les buf binaires)
log_path = os.path.join(out_dir, "call_log.json")
log_slim = []
for c in call_log:
    entry = {"fn": c["fn"], "args": c["args"], "ret": c["ret"]}
    # Inclure les buffers non-FPGA (petits writes de registres + PSM)
    if c.get("buf") and c["fn"] != "PHI_Write" or (
        c["fn"] == "PHI_Write" and c["args"][1] != 6 and c.get("buf")
    ):
        entry["buf"] = c["buf"]
    if c.get("bufAfter"):
        entry["bufAfter"] = c["bufAfter"]
    log_slim.append(entry)
with open(log_path, "w") as f:
    json.dump(log_slim, f, indent=2)
print(f"\nCall log sauvegarde : {log_path} ({len(call_log)} appels)")

# Sauvegarder le bitfile FPGA complet
if fpga_buf:
    fpga_path = os.path.join(out_dir, f"fpga_{len(fpga_buf)}B.bin")
    with open(fpga_path, "wb") as f:
        f.write(fpga_buf)
    print(f"Bitfile FPGA sauvegarde : {fpga_path} ({len(fpga_buf)} octets)")

print(f"Buffers PSM sauvegardes : {psm_idx} fichiers dans {out_dir}")

session.detach()
