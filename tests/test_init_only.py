"""
Test d'initialisation seule (sans GUI).
Lance le bridge32, execute initialize_full, affiche les resultats et le log.

Usage:
    python test_init_only.py
"""

import json
import os
import socket
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 9500
PYTHON32 = r"C:\Python311-32\python.exe"
BRIDGE   = os.path.join(os.path.dirname(__file__), "bridge", "bridge32.py")
PHI_DIR  = os.path.join(os.path.dirname(__file__), "bridge", "phi_binaries")
FPGA_BIN = os.path.join(PHI_DIR, "fpga_189956B.bin")
LOG_FILE = os.path.join(os.path.dirname(__file__), "bridge", "bridge32.log")
XML_MAP  = r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Register Map.xml"
CALL_LOG = os.path.join(PHI_DIR, "call_log.json")

PSM_BINS = sorted([
    os.path.join(PHI_DIR, f) for f in os.listdir(PHI_DIR)
    if f.startswith("psm_") and f.endswith(".bin")
])


def send_cmd(sock, cmd, args=None, timeout=120.0):
    req = {"id": 1, "cmd": cmd, "args": args or [], "kwargs": {}}
    sock.settimeout(timeout)
    sock.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("bridge ferme")
        buf += chunk
    resp = json.loads(buf.split(b"\n", 1)[0].decode())
    if resp.get("error"):
        raise RuntimeError(resp["error"])
    return resp["result"]


def main():
    # 1. Tuer tout bridge existant
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect((HOST, PORT))
        s.sendall((json.dumps({"id": 0, "cmd": "shutdown", "args": []}) + "\n").encode())
        s.close()
        time.sleep(1.0)
    except Exception:
        pass

    # 2. Lancer le bridge
    print(f"Lancement du bridge: {PYTHON32} {BRIDGE}")
    proc = subprocess.Popen(
        [PYTHON32, BRIDGE, "--port", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    # Attendre que le bridge soit pret
    ready = False
    for _ in range(20):
        line = proc.stdout.readline()
        if "[bridge32]" in line:
            print("Bridge pret:", line.strip())
            ready = True
            break
        time.sleep(0.3)
    if not ready:
        print("ERREUR: bridge pas demarre")
        proc.kill()
        return

    time.sleep(0.5)

    # 3. Connecter et initialiser
    sock = socket.socket()
    sock.connect((HOST, PORT))

    print(f"\nFPGA bin: {FPGA_BIN} ({os.path.getsize(FPGA_BIN)}B)")
    print(f"PSM bins: {[os.path.basename(p) for p in PSM_BINS]}")
    print(f"Call log: {CALL_LOG}")
    print(f"XML map:  {XML_MAP}\n")

    print("=== initialize_full (timeout 120s) ===")
    t0 = time.time()
    try:
        result = send_cmd(sock, "initialize_full", [
            os.path.abspath(FPGA_BIN),
            [os.path.abspath(p) for p in PSM_BINS],
            os.path.abspath(XML_MAP),
            os.path.abspath(CALL_LOG),
        ], timeout=120.0)
        print(f"initialize_full OK en {time.time()-t0:.1f}s : {result}")
    except Exception as e:
        print(f"initialize_full ERREUR ({time.time()-t0:.1f}s): {e}")

    # 4. Lire le log
    print("\n=== bridge32.log (100 dernieres lignes) ===")
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-100:]:
            print(line, end="")
    except Exception as e:
        print(f"Log illisible: {e}")

    # 5. Tester PHI_ReadARM_ADC_Data
    print("\n=== PHI_ReadARM_ADC_Data (selector 0..3, 5 lectures) ===")
    for sel in range(4):
        vals = []
        for _ in range(5):
            try:
                r = send_cmd(sock, "read_arm_adc_data", [sel], timeout=5.0)
                vals.append(r["value"])
            except Exception as ex:
                vals.append(f"ERR:{ex}")
            time.sleep(0.01)
        nz = sum(1 for v in vals if isinstance(v, int) and v != 0)
        print(f"  sel={sel}: {vals}  nz={nz}/5")

    # 6. Shutdown
    try:
        send_cmd(sock, "shutdown", timeout=5.0)
    except Exception:
        pass
    sock.close()
    proc.wait(timeout=5)
    print("\nTest termine.")


if __name__ == "__main__":
    main()
