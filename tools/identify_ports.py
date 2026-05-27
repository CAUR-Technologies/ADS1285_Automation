"""
Mappage des ports série du banc ADS1285 → config.ini.

Interroge chaque port avec les deux protocoles du banc et permet d'assigner
chaque instrument (Wavetek, APS Ctrl V, APS Ctrl H) à son port COM, puis
sauvegarde dans config.ini.

Lecture seule côté instruments : envoie uniquement des requêtes d'identification
  - APS 0109   : 19200 8N1, terminaison \\x00, "FWV?"/"SER?"
  - Wavetek 39A : 9600 8N1, terminaison CRLF, "*IDN?"

Usage :
    python tools/identify_ports.py            # interface graphique (défaut)
    python tools/identify_ports.py --cli      # scan en mode texte
    python tools/identify_ports.py --cli COM5 COM6   # ports précis
"""

import os
import sys
import time
import threading

import serial
from serial.tools import list_ports

# Racine du projet sur le path pour importer config/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config_manager as cfg  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Identification (réutilisable CLI + GUI)
# ─────────────────────────────────────────────────────────────────────────

def _read_until(ser, terminator=b"\x00", max_bytes=256):
    out = b""
    while len(out) < max_bytes:
        b = ser.read(1)
        if not b or b == terminator:
            break
        out += b
    return out.decode("ascii", errors="replace").strip()


APS_BAUDS = [19200, 9600, 38400, 4800, 2400]


def try_aps(port, baud=19200):
    """Retourne (firmware, serial) si un APS 0109 répond, sinon None."""
    try:
        with serial.Serial(port, baud, bytesize=8, parity="N",
                           stopbits=1, timeout=1.0) as s:
            s.write(b"FWV?\x00")
            time.sleep(0.15)
            fwv = _read_until(s)
            s.reset_input_buffer()
            s.write(b"SER?\x00")
            time.sleep(0.15)
            ser_num = _read_until(s)
            # Réponse APS valide -> se termine par "OK". Évite les faux positifs
            # (octets brouillés à un mauvais baud).
            if "OK" in fwv.upper() or "OK" in ser_num.upper():
                return (fwv, ser_num)
    except Exception:
        pass
    return None


def try_wavetek(port):
    """Retourne la chaîne *IDN? si un Wavetek répond, sinon None."""
    try:
        with serial.Serial(port, 9600, bytesize=8, parity="N",
                           stopbits=1, timeout=1.0) as s:
            s.write(b"*IDN?\r\n")
            time.sleep(0.15)
            resp = s.readline().decode("ascii", errors="replace").strip()
            if resp:
                return resp
    except Exception:
        pass
    return None


def identify_port(port):
    """Retourne un dict {kind, detail, serial} pour un port."""
    aps = try_aps(port)
    if aps:
        fwv, ser_num = aps
        return {"kind": "APS 0109", "detail": f"fw={fwv}", "serial": ser_num}
    wav = try_wavetek(port)
    if wav:
        return {"kind": "Wavetek", "detail": wav, "serial": ""}
    return {"kind": "", "detail": "", "serial": ""}


def list_serial_ports(skip_bluetooth=True):
    """Liste [(device, description)] des ports COM."""
    ports = []
    for p in list_ports.comports():
        desc = p.description or ""
        if skip_bluetooth and "bluetooth" in desc.lower():
            continue
        ports.append((p.device, desc))
    return ports


# ─────────────────────────────────────────────────────────────────────────
# Mode CLI
# ─────────────────────────────────────────────────────────────────────────

def main_cli(argv):
    scan_baud = "--scan-baud" in argv
    ports = [a for a in argv if not a.startswith("--")] \
        or [d for d, _ in list_serial_ports()]
    if not ports:
        print("Aucun port à scanner.")
        return
    print(f"Scan de : {', '.join(ports)}"
          + (" (balayage baud APS)" if scan_baud else "") + "\n")
    for port in ports:
        print(f"--- {port} ---")
        if scan_baud:
            found = False
            for baud in APS_BAUDS:
                aps = try_aps(port, baud)
                if aps:
                    print(f"  → APS 0109 @ {baud} baud "
                          f"(série={aps[1]!r}, fw={aps[0]!r})")
                    found = True
            if not found:
                print(f"  → aucune réponse APS à {APS_BAUDS}")
            continue
        info = identify_port(port)
        if info["kind"] == "APS 0109":
            print(f"  → APS 0109  (série={info['serial']!r}, {info['detail']})")
            print("    Note la série pour distinguer l'axe V de H.")
        elif info["kind"] == "Wavetek":
            print(f"  → Wavetek   (*IDN? = {info['detail']!r})")
        else:
            print("  → aucun instrument reconnu (éteint, non câblé, ou autre).")
    print("\nReporte les COM dans config.ini ou via l'interface (sans --cli).")


# ─────────────────────────────────────────────────────────────────────────
# Mode GUI
# ─────────────────────────────────────────────────────────────────────────

def build_port_mapper(root):
    """Construit l'interface de mappage dans la fenêtre Tk fournie."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    NONE_LABEL = "(aucun)"

    root.title("Mappage des ports — Banc ADS1285")
    root.geometry("680x460")

    ttk.Label(root, text="Scanne les ports série, identifie les instruments, "
                         "assigne-les puis sauvegarde dans config.ini.",
              wraplength=660).pack(anchor="w", padx=10, pady=(10, 4))

    # --- Barre scan ---
    top = ttk.Frame(root)
    top.pack(fill="x", padx=10, pady=4)
    btn_scan = ttk.Button(top, text="Scanner & identifier")
    btn_scan.pack(side="left")
    lbl_status = ttk.Label(top, text="")
    lbl_status.pack(side="left", padx=10)

    # --- Tableau des ports détectés ---
    cols = ("desc", "detected", "serial")
    tree = ttk.Treeview(root, columns=cols, show="headings", height=7)
    tree.heading("desc", text="Description")
    tree.heading("detected", text="Détecté")
    tree.heading("serial", text="Série / IDN")
    tree.column("desc", width=300)
    tree.column("detected", width=110)
    tree.column("serial", width=210)
    tree.pack(fill="x", padx=10, pady=4)
    # 1ère colonne = port (heading text)
    tree.heading("#0", text="Port")
    tree.column("#0", width=70)

    # --- Assignation ---
    assign = ttk.LabelFrame(root, text="  Assignation")
    assign.pack(fill="x", padx=10, pady=6)
    assign.columnconfigure(1, weight=1)

    cur = cfg.get
    rows = [
        ("Wavetek :",      "wavetek",  cur("Wavetek", "port")),
        ("APS Ctrl V :",   "aps_v",    cur("APS", "controller_vertical_port")),
        ("APS Ctrl H :",   "aps_h",    cur("APS", "controller_horizontal_port")),
    ]
    combos = {}
    for i, (label, key, current) in enumerate(rows):
        ttk.Label(assign, text=label).grid(row=i, column=0, sticky="w",
                                           padx=6, pady=4)
        var = tk.StringVar(value=current or NONE_LABEL)
        cb = ttk.Combobox(assign, textvariable=var, state="readonly", width=24)
        cb.grid(row=i, column=1, sticky="w", padx=6, pady=4)
        combos[key] = (cb, var)

    # --- Sauvegarde ---
    bottom = ttk.Frame(root)
    bottom.pack(fill="x", padx=10, pady=8)
    btn_save = ttk.Button(bottom, text="Sauvegarder dans config.ini")
    btn_save.pack(side="left")
    lbl_save = ttk.Label(bottom, text="")
    lbl_save.pack(side="left", padx=10)

    def refresh_combo_values(ports):
        values = [NONE_LABEL] + ports
        for cb, _ in combos.values():
            cb.configure(values=values)

    # Remplir les comboboxes avec les ports actuels dès l'ouverture
    initial_ports = [d for d, _ in list_serial_ports(skip_bluetooth=False)]
    refresh_combo_values(initial_ports)

    def do_scan():
        btn_scan.configure(state="disabled")
        lbl_status.configure(text="Scan en cours…")
        for it in tree.get_children():
            tree.delete(it)

        def worker():
            results = []
            for device, desc in list_serial_ports(skip_bluetooth=False):
                if "bluetooth" in desc.lower():
                    results.append((device, desc, {"kind": "(Bluetooth)",
                                                    "detail": "", "serial": ""}))
                    continue
                results.append((device, desc, identify_port(device)))
            root.after(0, lambda: finish_scan(results))

        threading.Thread(target=worker, daemon=True).start()

    def finish_scan(results):
        all_ports = [d for d, _, _ in results]
        refresh_combo_values(all_ports)
        wavetek_port = None
        aps_ports = []
        for device, desc, info in results:
            tree.insert("", "end", text=device,
                        values=(desc, info["kind"],
                                info["serial"] or info["detail"]))
            if info["kind"] == "Wavetek":
                wavetek_port = device
            elif info["kind"] == "APS 0109":
                aps_ports.append(device)
        # Auto-remplissage (l'utilisateur ajuste V/H via les séries)
        if wavetek_port:
            combos["wavetek"][1].set(wavetek_port)
        if len(aps_ports) >= 1:
            combos["aps_v"][1].set(aps_ports[0])
        if len(aps_ports) >= 2:
            combos["aps_h"][1].set(aps_ports[1])
        lbl_status.configure(
            text=f"{len(results)} port(s) — {len(aps_ports)} APS, "
                 f"{'1' if wavetek_port else '0'} Wavetek")
        btn_scan.configure(state="normal")

    def do_save():
        vals = {k: v.get() for k, (_, v) in combos.items()}
        chosen = [p for p in vals.values() if p != NONE_LABEL]
        # Avertir si doublon de port
        if len(set(chosen)) != len(chosen):
            messagebox.showwarning("Mappage",
                                   "Un même port est assigné à deux instruments.")
            return
        if vals["wavetek"] != NONE_LABEL:
            cfg.set_value("Wavetek", "port", vals["wavetek"])
        if vals["aps_v"] != NONE_LABEL:
            cfg.set_value("APS", "controller_vertical_port", vals["aps_v"])
        if vals["aps_h"] != NONE_LABEL:
            cfg.set_value("APS", "controller_horizontal_port", vals["aps_h"])
        cfg.save()
        lbl_save.configure(text=f"Sauvegardé dans {os.path.basename(cfg.CONFIG_FILE)}")

    btn_scan.configure(command=do_scan)
    btn_save.configure(command=do_save)


def main_gui():
    import tkinter as tk
    root = tk.Tk()
    build_port_mapper(root)
    root.mainloop()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--cli"]
        main_cli(args)
    else:
        main_gui()
