"""
Probe série interactif — débogage d'instruments RS-232 (Wavetek, APS…).

Envoie ce que tu tapes (terminateur + baud réglables), affiche la réponse brute
en ASCII et en hexa. Sert à découvrir/valider le vrai jeu de commandes d'un
instrument quand le driver suppose un protocole qui ne marche pas.

Usage :
    python tools/serial_probe.py COM6
    python tools/serial_probe.py COM6 --baud 19200 --eol cr

Dans l'invite :
    <texte>          envoie <texte> + terminateur, montre la réponse
    \\eol crlf|cr|lf|none   change le terminateur
    \\baud 19200            rouvre le port à ce baud
    \\scan <cmd>            essaie <cmd> à 4800/9600/19200/38400, montre qui répond
    \\raw <hexa>            envoie des octets bruts (ex: \\raw 2A49444E3F0D0A)
    \\quit
"""

import sys
import time
import argparse

import serial

EOL = {"crlf": b"\r\n", "cr": b"\r", "lf": b"\n", "none": b""}
COMMON_BAUDS = [4800, 9600, 19200, 38400]


def send_recv(ser, payload: bytes, wait=0.2, max_bytes=512):
    ser.reset_input_buffer()
    ser.write(payload)
    time.sleep(wait)
    out = b""
    while len(out) < max_bytes:
        chunk = ser.read(256)
        if not chunk:
            break
        out += chunk
    return out


def show(resp: bytes):
    if not resp:
        print("  ← (rien / timeout)")
        return
    ascii_view = resp.decode("ascii", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
    hex_view = resp.hex(" ")
    print(f"  ← ASCII: {ascii_view!r}")
    print(f"  ← HEX  : {hex_view}")


def scan_baud(port, cmd, eol):
    print(f"Scan baud pour {cmd!r} :")
    for baud in COMMON_BAUDS:
        try:
            with serial.Serial(port, baud, timeout=0.8) as s:
                resp = send_recv(s, cmd.encode("ascii") + eol)
            tag = "RÉPONSE" if resp else "rien"
            print(f"  {baud:>6} baud → {tag}"
                  + (f" : {resp.decode('ascii', errors='replace')!r}" if resp else ""))
        except Exception as e:
            print(f"  {baud:>6} baud → erreur: {e}")


def main():
    ap = argparse.ArgumentParser(description="Probe série interactif")
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--eol", choices=list(EOL), default="crlf")
    args = ap.parse_args()

    baud = args.baud
    eol = EOL[args.eol]
    eol_name = args.eol

    def open_port():
        return serial.Serial(args.port, baud, bytesize=8, parity="N",
                             stopbits=1, timeout=0.8)

    print(f"Probe {args.port} @ {baud} baud, eol={eol_name}. "
          f"Tape une commande, ou \\quit. (\\help pour l'aide)")
    ser = open_port()
    try:
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line.startswith("\\"):
                parts = line[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                if cmd in ("quit", "q", "exit"):
                    break
                elif cmd == "help":
                    print(__doc__)
                elif cmd == "eol" and arg in EOL:
                    eol, eol_name = EOL[arg], arg
                    print(f"  terminateur = {eol_name}")
                elif cmd == "baud" and arg.isdigit():
                    baud = int(arg)
                    ser.close()
                    ser = open_port()
                    print(f"  rouvert à {baud} baud")
                elif cmd == "scan" and arg:
                    scan_baud(args.port, arg, eol)
                elif cmd == "raw" and arg:
                    try:
                        payload = bytes.fromhex(arg.replace(" ", ""))
                        show(send_recv(ser, payload))
                    except ValueError:
                        print("  hexa invalide")
                else:
                    print("  commande probe inconnue (\\help)")
                continue
            # Commande instrument
            show(send_recv(ser, line.encode("ascii") + eol))
    finally:
        ser.close()
        print("Port fermé.")


if __name__ == "__main__":
    main()
