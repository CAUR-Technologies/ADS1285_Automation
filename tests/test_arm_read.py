"""
Test de PHI_ReadARM_ADC_Data via le bridge.

Prerequis : gui.py ouvert + ADS1285 connecte (le bridge tourne et est initialise),
OU bridge lance manuellement et initialise.

1. Balaye plusieurs valeurs de 'selector' (arg2) avec quelques lectures chacune,
   pour reperer celle(s) qui renvoient des valeurs non-nulles et variables.
2. Fait une acquisition en boucle (acquire_arm) avec le meilleur selector.

Genere des vibrations/chocs pendant le test pour voir si les valeurs bougent.
"""

import json
import socket
import time

HOST, PORT = "127.0.0.1", 9500
_id = 0


def call(sock, cmd, args=None, timeout=30.0):
    global _id
    _id += 1
    sock.settimeout(timeout)
    req = {"id": _id, "cmd": cmd, "args": args or [], "kwargs": {}}
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
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    print("=== Balayage des selectors (10 lectures chacun) ===")
    good = []
    for sel in range(0, 8):
        vals = []
        rets = []
        for _ in range(10):
            r = call(sock, "read_arm_adc_data", [sel])
            vals.append(r["value"])
            rets.append(r["ret"])
            time.sleep(0.005)
        nz = sum(1 for v in vals if v != 0)
        distinct = len(set(vals))
        flag = ""
        if nz > 0 and distinct > 1:
            flag = "  <-- non-nul ET variable"
            good.append(sel)
        elif nz > 0:
            flag = "  (non-nul mais constant)"
        print(f"  selector={sel}: ret={rets[0]} nz={nz}/10 distinct={distinct} ex={vals[:4]}{flag}")

    # Choisir le selector : premier 'bon', sinon 0
    sel = good[0] if good else 0
    print(f"\n=== Acquisition de 512 samples avec selector={sel} ===")
    print("    (genere des chocs MAINTENANT)")
    r = call(sock, "acquire_arm", [512, sel, 0])
    data = r["data"]
    nz = sum(1 for v in data if v != 0)
    print(f"  recu {len(data)} samples, non_zero={nz}")
    if data:
        print(f"  min={min(data)} max={max(data)} amplitude={max(data)-min(data)}")
        print(f"  premiers 8: {data[:8]}")
        print(f"  derniers 8: {data[-8:]}")

    sock.close()


if __name__ == "__main__":
    main()
