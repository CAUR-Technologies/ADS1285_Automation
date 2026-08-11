"""
Panneau de contrôle DÉDIÉ — caractérisation d'une unité géophone 3 axes (STREAM).

Fenêtre autonome (séparée du GUI mono-géophone `gui.py`) pour que l'opérateur
pilote lui-même le banc en toute sécurité :

  * connexion instruments (Wavetek + APS de l'axe + accéléro NI),
  * découverte de l'unité 3 axes (USB CDC) + réglage gain,
  * centrage ZER, puis balayage en fréquence (voie STREAM) avec table live des
    sensibilités PAR VOIE,
  * panneau GNSS / 1PPS (cohérence : NMEA sur port série + 1PPS sur PFI0 NI),
  * **gros bouton ARRÊT** qui coupe l'excitation immédiatement, + garde-fous servo
    (accéléro muet → arrêt) hérités de `TestBench`.

Lancer :  python gui_3axis.py
"""

import csv
import datetime
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from equipment.wavetek import Wavetek39A
from equipment.aps import APSController
from equipment.accelerometer.accelerometer import Accelerometer
from equipment.testbench import TestBench, TestBenchAborted
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from equipment.geophone3axis.session import Characterize3AxisSession
from config.settings import (
    WAVETEK_PORT, WAVETEK_BAUD,
    APS_CONTROLLER_HORIZONTAL_PORT, APS_CONTROLLER_VERTICAL_PORT,
    NI_DEVICE_NAME, NI_AI_CHANNELS, NI_SAMPLE_RATE, NI_SAMPLES_PER_CHANNEL,
    NI_REF_CHANNEL_HORIZONTAL, NI_REF_CHANNEL_VERTICAL, SHAKER_STIFFNESS_SCHEDULE,
    GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID, GEOPHONE3AXIS_DATA_DIR,
    GNSS_PORT, GNSS_BAUD, GNSS_NI_DEVICE, GNSS_PFI_TERMINAL, GNSS_COUNTER,
)

# Pleine échelle unité 3 axes = ADS1285 : ±2,5 V à gain 1 (VREF/1,6384, datasheet).
FULLSCALE_VPK = 2.5
# Garde-fou : plafond Vpp prudent pour le banc 3 axes (bien sous le 5 V d'origine).
SERVO_VPP_MAX_3AXIS = 1.5
AXIS_MAP = "voie 1 = X · voie 2 = Y · voie 3 = Z"


class ThreeAxisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Caractérisation 3 axes — banc géophones")
        self.geometry("1080x720")

        self.bench: TestBench | None = None
        self.wav = self.aps = self.accel = None
        self.unit: Geophone3Axis | None = None
        self.unit_serial = ""
        self._stop_event = threading.Event()
        self._busy = False
        self._zer_done = False   # sécurité : pas d'excitation avant centrage ZER
        self._csv_file = None
        self._csv = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────── UI
    def _build_ui(self):
        left = ttk.Frame(self, padding=8); left.pack(side="left", fill="y")
        right = ttk.Frame(self, padding=8); right.pack(side="right", fill="both", expand=True)

        # -- Instruments --
        fi = ttk.LabelFrame(left, text="1 · Instruments (shaker)", padding=6)
        fi.pack(fill="x", pady=4)
        self.axis = tk.StringVar(value="horizontal")
        ttk.Radiobutton(fi, text="Horizontal (COM14 · ai0)", value="horizontal",
                        variable=self.axis).grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Radiobutton(fi, text="Vertical (COM8 · ai1)", value="vertical",
                        variable=self.axis).grid(row=1, column=0, sticky="w", columnspan=2)
        self.btn_conn = ttk.Button(fi, text="Connecter instruments", command=self._connect_instruments)
        self.btn_conn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)
        self.lbl_instr = ttk.Label(fi, text="non connecté", foreground="gray")
        self.lbl_instr.grid(row=3, column=0, columnspan=2, sticky="w")

        # -- Unité 3 axes --
        fu = ttk.LabelFrame(left, text="2 · Unité 3 axes (USB)", padding=6)
        fu.pack(fill="x", pady=4)
        ttk.Button(fu, text="Découvrir l'unité", command=self._discover_unit).grid(
            row=0, column=0, columnspan=2, sticky="ew")
        self.lbl_unit = ttk.Label(fu, text="—", foreground="gray")
        self.lbl_unit.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(fu, text="Gain ADC :").grid(row=2, column=0, sticky="w")
        self.gain = tk.StringVar(value="1")
        ttk.Combobox(fu, textvariable=self.gain, values=["1", "2", "4", "8"],
                     width=5, state="readonly").grid(row=2, column=1, sticky="w")
        ttk.Label(fu, text=AXIS_MAP, foreground="#555").grid(row=3, column=0, columnspan=2, sticky="w")

        # -- GNSS / 1PPS --
        fg = ttk.LabelFrame(left, text="3 · GNSS / 1PPS (cohérence)", padding=6)
        fg.pack(fill="x", pady=4)
        ttk.Button(fg, text="Vérifier GNSS + 1PPS", command=self._check_gnss).grid(
            row=0, column=0, sticky="ew")
        self.lbl_gnss = ttk.Label(fg, text="NMEA : —", foreground="gray")
        self.lbl_gnss.grid(row=1, column=0, sticky="w")
        self.lbl_pps = ttk.Label(fg, text="1PPS PFI0 : —", foreground="gray")
        self.lbl_pps.grid(row=2, column=0, sticky="w")

        # -- Balayage --
        fs = ttk.LabelFrame(left, text="4 · Balayage", padding=6)
        fs.pack(fill="x", pady=4)
        ttk.Label(fs, text="Fréquences (Hz) :").grid(row=0, column=0, sticky="w")
        # Balayage par défaut 1–100 Hz (bande utile du géophone). Les BF < 1 Hz de la
        # sweep mono-géophone sont RETIRÉES ici : à 0,1 Hz un palier prend ~4 min
        # (fenêtres servo ~20 s + dwell 60 s), pour un signal minuscule (roll-off f²,
        # SNR pourri) et un grand déplacement (risque butée). Les rajouter à la main
        # si besoin. Balayé HAUTE→BASSE (anti-butée).
        self.freqs = tk.StringVar(value="1, 2, 5, 10, 20, 50, 70, 100")
        ttk.Entry(fs, textvariable=self.freqs, width=18).grid(row=0, column=1, sticky="w")
        ttk.Label(fs, text="Enveloppe :").grid(row=1, column=0, sticky="w")
        self.envelope = tk.StringVar(value="0.3")
        ttk.Entry(fs, textvariable=self.envelope, width=6).grid(row=1, column=1, sticky="w")
        ttk.Label(fs, text="V max géo (m/s) :").grid(row=2, column=0, sticky="w")
        self.vmax = tk.StringVar(value="0.006")
        ttk.Entry(fs, textvariable=self.vmax, width=6).grid(row=2, column=1, sticky="w")
        # Mesure = .dat 250 Hz par DÉFAUT (SNR fiable, timing GPS). Le STREAM 50 Hz
        # (sous-estime, masque la résonance) n'est plus qu'un check rapide optionnel.
        self.quick_check = tk.BooleanVar(value=False)
        ttk.Checkbutton(fs, text="Check rapide STREAM (sans enregistrement)",
                        variable=self.quick_check).grid(row=3, column=0, columnspan=2, sticky="w")
        self.btn_zer = ttk.Button(fs, text="Centrer ZER", command=self._center_zer, state="disabled")
        self.btn_zer.grid(row=4, column=0, columnspan=2, sticky="ew", pady=2)
        self.btn_run = ttk.Button(fs, text="▶ LANCER le balayage", command=self._run_sweep, state="disabled")
        self.btn_run.grid(row=5, column=0, columnspan=2, sticky="ew", pady=2)
        self.btn_stop = tk.Button(fs, text="⛔ ARRÊT", command=self._stop, state="disabled",
                                  bg="#c0392b", fg="white", font=("Segoe UI", 12, "bold"), height=2)
        self.btn_stop.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)

        # -- Résultats --
        ttk.Label(right, text="Sensibilité par fréquence (voie sur-axe = max)").pack(anchor="w")
        cols = ("freq", "accel", "onaxis", "scnt", "sv", "snr")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=10)
        for c, t, w in (("freq", "Fréq (Hz)", 70), ("accel", "a (mg)", 70),
                        ("onaxis", "Voie sur-axe", 90), ("scnt", "S counts/(m/s)", 120),
                        ("sv", "S V/(m/s)", 90), ("snr", "SNR (dB)", 70)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="x", pady=4)

        ttk.Label(right, text="Journal").pack(anchor="w")
        self.log = tk.Text(right, height=18, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    # ─────────────────────────────────────────────────────── helpers UI
    def _logln(self, msg):
        self.after(0, self.__logln, str(msg))

    def __logln(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n"); self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy):
        self._busy = busy
        if busy:
            for b in (self.btn_conn, self.btn_zer, self.btn_run):
                b.configure(state="disabled")
            self.btn_stop.configure(state="normal")
        else:
            self.btn_conn.configure(state="normal")
            self.btn_zer.configure(state="normal" if self.bench else "disabled")
            # LANCER seulement si instruments connectés ET ZER fait (anti-butée).
            self.btn_run.configure(state="normal" if (self.bench and self._zer_done) else "disabled")
            self.btn_stop.configure(state="disabled")

    # ─────────────────────────────────────────────────────── actions
    def _connect_instruments(self):
        try:
            axis = self.axis.get()
            self.wav = Wavetek39A(port=WAVETEK_PORT, baud=WAVETEK_BAUD); self.wav.connect()
            port = APS_CONTROLLER_HORIZONTAL_PORT if axis == "horizontal" else APS_CONTROLLER_VERTICAL_PORT
            self.aps = APSController(axis=axis, port=port); self.aps.connect()
            ref = NI_REF_CHANNEL_HORIZONTAL if axis == "horizontal" else NI_REF_CHANNEL_VERTICAL
            self.accel = Accelerometer(device=NI_DEVICE_NAME, channels=NI_AI_CHANNELS,
                                       sample_rate=NI_SAMPLE_RATE,
                                       samples_per_channel=NI_SAMPLES_PER_CHANNEL, ref_channel=ref)
            self.accel.connect()
            self.bench = TestBench(self.wav, self.aps, self.accel, None,
                                   envelope_fraction=float(self.envelope.get()),
                                   geophone_max_velocity_mps=float(self.vmax.get()),
                                   vpp_max=SERVO_VPP_MAX_3AXIS,
                                   stiffness_schedule=SHAKER_STIFFNESS_SCHEDULE.get(axis),
                                   ref_channel=ref)
            self.bench.set_logger(self._logln)
            self.bench.set_stop_event(self._stop_event)
            self.lbl_instr.configure(text=f"connecté ({axis}, ai{ref})", foreground="green")
            # LANCER reste VERROUILLÉ tant que le ZER n'est pas fait (règle du banc :
            # centrage avant tout signal AC — sinon l'armature décentrée part en butée).
            self._zer_done = False
            self.btn_zer.configure(state="normal")
            self.btn_run.configure(state="disabled")
            self._logln(f"Instruments connectés (axe {axis}, vpp_max {SERVO_VPP_MAX_3AXIS} V). "
                        f"→ Centrer ZER avant de pouvoir lancer.")
        except Exception as e:
            messagebox.showerror("Instruments", str(e))

    def _discover_unit(self):
        try:
            u = discover_units(vid=GEOPHONE3AXIS_VID, pid=GEOPHONE3AXIS_PID)
            if not u:
                self.lbl_unit.configure(text="aucune unité détectée", foreground="red"); return
            self.unit_serial, port = u[0]
            self.unit = Geophone3Axis(port, serial_number=self.unit_serial); self.unit.connect()
            st = self.unit.status()
            self.lbl_unit.configure(text=f"{self.unit_serial} @ {port} (fw {st.get('fw','?')})",
                                    foreground="green")
            self._logln(f"Unité {self.unit_serial} connectée.")
        except Exception as e:
            messagebox.showerror("Unité 3 axes", str(e))

    def _check_gnss(self):
        threading.Thread(target=self._check_gnss_worker, daemon=True).start()

    def _check_gnss_worker(self):
        # NMEA sur port série
        try:
            from equipment.gnss.gnss import Gnss
            g = Gnss(port=GNSS_PORT, baud=GNSS_BAUD); g.connect()
            fix = g.read_fix(timeout=4.0); g.disconnect()
            if fix and fix.get("fix_quality", 0) > 0:
                txt = (f"NMEA {GNSS_PORT} : fix={fix['fix_quality']} sats={fix['num_sats']} "
                       f"UTC={fix.get('utc_hhmmss','?')} HDOP={fix.get('hdop','?')}")
                col = "green"
            else:
                txt = f"NMEA {GNSS_PORT} : pas de fix"; col = "red"
        except Exception as e:
            txt = f"NMEA {GNSS_PORT} : erreur ({e})"; col = "red"
        self.after(0, lambda: self.lbl_gnss.configure(text=txt, foreground=col))
        # 1PPS sur PFI0 (comptage direct des fronts)
        try:
            import nidaqmx
            from nidaqmx.constants import Edge
            import time as _t
            task = nidaqmx.Task()
            ch = task.ci_channels.add_ci_count_edges_chan(f"{GNSS_NI_DEVICE}/{GNSS_COUNTER}", edge=Edge.RISING)
            ch.ci_count_edges_term = f"/{GNSS_NI_DEVICE}/{GNSS_PFI_TERMINAL}"
            task.start(); t0 = _t.time(); base = int(task.read()); _t.sleep(4.0)
            n = int(task.read()) - base; dt = _t.time() - t0
            task.stop(); task.close()
            hz = n / dt
            ok = 0.8 <= hz <= 1.2
            ptxt = f"1PPS {GNSS_PFI_TERMINAL} : {n} fronts / {dt:.1f}s = {hz:.2f} Hz"
            pcol = "green" if ok else "red"
        except Exception as e:
            ptxt = f"1PPS {GNSS_PFI_TERMINAL} : erreur ({e})"; pcol = "red"
        self.after(0, lambda: self.lbl_pps.configure(text=ptxt, foreground=pcol))

    def _center_zer(self):
        if not self.bench:
            return
        self._set_busy(True); self._stop_event.clear()

        def work():
            ok = False
            try:
                z = self.bench.center_zero()
                self._logln(f"ZER = {z}")
                ok = True
            except Exception as e:
                self._logln(f"ZER échec : {e}")
            finally:
                self.after(0, lambda: self._finish_zer(ok))
        threading.Thread(target=work, daemon=True).start()

    def _finish_zer(self, ok):
        self._zer_done = ok
        self._set_busy(False)
        if ok:
            self.btn_run.configure(state="normal")   # LANCER déverrouillé
            self._logln("ZER fait → balayage autorisé.")

    def _run_sweep(self):
        if not self.bench or not self.unit:
            messagebox.showwarning("Balayage", "Connecter les instruments ET découvrir l'unité d'abord.")
            return
        if not self._zer_done:   # sécurité : centrage avant tout signal AC (anti-butée)
            messagebox.showwarning("Balayage", "Centrer le ZER d'abord (armature centrée = pas de butée).")
            return
        try:
            freqs = [float(x.strip()) for x in self.freqs.get().split(",") if x.strip()]
            gain = int(self.gain.get())
        except ValueError:
            messagebox.showerror("Balayage", "Fréquences ou gain invalides."); return
        for it in self.tree.get_children():
            self.tree.delete(it)
        self._set_busy(True); self._stop_event.clear()
        lsb_v = FULLSCALE_VPK / gain / (2 ** 31)
        self._open_csv(gain)

        rec_dat = not self.quick_check.get()   # .dat = mesure par défaut ; STREAM = check
        pts: list = []

        def on_point(p):
            pts.append(p)
            self.after(0, self._add_row, p, lsb_v)

        def work():
            gnss = None
            try:
                self.unit.set_config({"gain": gain})
                if rec_dat:
                    from equipment.gnss.gnss import Gnss
                    from config.settings import GNSS_PORT, GNSS_BAUD
                    gnss = Gnss(port=GNSS_PORT, baud=GNSS_BAUD); gnss.connect()
                    # Unité en enregistrement 250 Hz pendant le balayage (fichiers
                    # ~3 s pour qu'ils se FERMENT en cours de run → récupérables).
                    self.unit.set_config({"sample_rate_hz": 250, "samples_by_record": 250,
                                          "records_per_file": 8, "survey_id": "BenchRun2"})
                sess = Characterize3AxisSession(self.bench, self.unit, gnss, None,
                                                GEOPHONE3AXIS_DATA_DIR)
                # ≥10 cycles par palier (essentiel en BF : à 0,1 Hz, 10 cycles = 100 s),
                # plafonné pour borner la durée totale. En STREAM (check) fenêtres courtes.
                sess.run_stream(freqs, excite=True, n_cycles=10,
                                min_duration_s=5.0 if rec_dat else 2.0,
                                max_duration_s=60.0 if rec_dat else 8.0, on_point=on_point,
                                start_unit=rec_dat, stream=not rec_dat)
                self._logln("Balayage STREAM terminé.")
                if rec_dat:
                    self._logln("Récupération .dat + corrélation 250 Hz (GPS)…")
                    dat = sess.correlate_dat_run(pts, lsb_v=lsb_v,
                                                 survey_path="/survey-data/BenchRun2")
                    self.after(0, self._log_dat_results, dat, list(pts))
            except TestBenchAborted as e:
                msg = str(e)
                self._logln(f"⛔ ARRÊT / sécurité : {msg}")
                self.after(0, lambda m=msg: messagebox.showwarning("Balayage arrêté", m))
            except Exception as e:
                msg = str(e)
                self._logln(f"Erreur : {msg}")
                self.after(0, lambda m=msg: messagebox.showerror("Balayage", m))
            finally:
                try:
                    self.wav.disable_output()
                except Exception:
                    pass
                if gnss is not None:
                    try:
                        gnss.disconnect()
                    except Exception:
                        pass
                self.after(0, self._sweep_done)
        threading.Thread(target=work, daemon=True).start()

    def _log_dat_results(self, dat, pts):
        """Repeuple la table + le journal avec la sensibilité .dat 250 Hz (voie
        sur-axe = max counts), timestamps GPS précis."""
        self._logln("=== Sensibilité .dat 250 Hz (timestamps GPS précis) ===")
        freqs = sorted({f for byf in dat.values() for f in byf}, reverse=True)
        if not freqs:
            self._logln("  (aucun .dat exploitable — fichiers non fermés / pas de fix GPS "
                        "sur l'unité)")
            return
        accel = {p["freq_hz"]: p.get("accel_g") for p in pts if not p.get("skipped")}
        for it in self.tree.get_children():   # remplace les lignes accéléro par les résultats .dat
            self.tree.delete(it)
        for f in freqs:
            best = None
            for cid, byf in dat.items():
                d = byf.get(f)
                if d and (best is None or d["counts_peak"] > best[1]["counts_peak"]):
                    best = (cid, d)
            if not best:
                continue
            cid, d = best
            a = accel.get(f)
            self.tree.insert("", "end", values=(
                f"{f:g}", f"{a*1e3:.2f}" if a else "—", f"voie {cid}",
                f"{d['sens_counts_per_mps']:.3g}", f"{d['sens_v_per_mps']:.1f}", f"n={d['n']}"))
            self._logln(f"  {f:>4g} Hz  voie {cid}  S = {d['sens_v_per_mps']:.1f} V/(m/s)  (n={d['n']})")

    # ------- sauvegarde CSV -------
    def _open_csv(self, gain):
        try:
            os.makedirs(GEOPHONE3AXIS_DATA_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(GEOPHONE3AXIS_DATA_DIR,
                                f"3axis_{self.unit_serial}_{self.axis.get()}_g{gain}_{ts}.csv")
            self._csv_file = open(path, "w", newline="", encoding="utf-8")
            self._csv = csv.writer(self._csv_file)
            hdr = ["freq_hz", "accel_g", "table_velocity_mps", "geo_fs", "on_axis"]
            for c in ("1", "2", "3"):
                hdr += [f"ch{c}_counts_pk", f"ch{c}_S_cnt_per_mps",
                        f"ch{c}_S_V_per_mps", f"ch{c}_snr_db"]
            self._csv.writerow(hdr); self._csv_file.flush()
            self._logln(f"→ sauvegarde : {path}")
        except Exception as e:
            self._csv = self._csv_file = None
            self._logln(f"(sauvegarde CSV indisponible : {e})")

    def _csv_row(self, p, lsb_v):
        if not self._csv:
            return
        if p.get("skipped"):
            self._csv.writerow([f"{p['freq_hz']:g}", "skipped", p.get("note", "")])
        else:
            ch = p["channels"]
            on_id = (max(ch.items(), key=lambda kv: kv[1]["counts_peak"])[0]
                     if ch else "")   # run .dat : pas de voies STREAM
            row = [f"{p['freq_hz']:g}", f"{p['accel_g']:.6g}",
                   f"{p.get('table_velocity_mps', float('nan')):.6g}",
                   f"{p.get('geo_fs', 0):.2f}", on_id]
            for c in ("1", "2", "3"):
                d = ch.get(c, {})
                scnt = d.get("sens_counts_per_mps", float("nan"))
                row += [f"{d.get('counts_peak', float('nan')):.6g}", f"{scnt:.6g}",
                        f"{scnt * lsb_v:.6g}", f"{d.get('snr_db', float('nan')):.1f}"]
            self._csv.writerow(row)
        self._csv_file.flush()

    def _sweep_done(self):
        if self._csv_file:
            try:
                self._csv_file.close()
            except Exception:
                pass
            self._csv = self._csv_file = None
        self._set_busy(False)

    def _add_row(self, p, lsb_v):
        self._csv_row(p, lsb_v)   # persiste toutes les voies + l'état
        if p.get("skipped"):
            self.tree.insert("", "end", values=(f"{p['freq_hz']:g}", "—", "IGNORÉ",
                                                 p.get("note", "")[:18], "—", "—"))
            return
        ch = p["channels"]
        if not ch:   # run .dat (stream=False) : pas de voies live → accéléro seul
            self.tree.insert("", "end", values=(
                f"{p['freq_hz']:g}", f"{p['accel_g']*1e3:.2f}", "→ .dat", "—", "—", "—"))
            return
        on_id, on = max(ch.items(), key=lambda kv: kv[1]["counts_peak"])
        s_v = on["sens_counts_per_mps"] * lsb_v
        self.tree.insert("", "end", values=(
            f"{p['freq_hz']:g}", f"{p['accel_g']*1e3:.2f}", f"voie {on_id}",
            f"{on['sens_counts_per_mps']:.3g}", f"{s_v:.1f}", f"{on['snr_db']:.0f}"))

    def _stop(self):
        # ARRÊT IMMÉDIAT : signale le thread ET coupe le Wavetek tout de suite.
        self._stop_event.set()
        try:
            if self.wav:
                self.wav.disable_output()
        except Exception:
            pass
        self._logln("⛔ ARRÊT demandé — excitation coupée.")

    def _on_close(self):
        # Toujours : signaler l'arrêt + COUPER L'EXCITATION (sécurité).
        try:
            self._stop_event.set()
            if self.wav:
                self.wav.disable_output()
        except Exception:
            pass
        # Si un run est EN COURS, NE PAS déconnecter les instruments ici : le worker
        # les utilise (acquisition NI/série en cours) → conflit thread principal ↔
        # worker → GEL. On ferme juste la fenêtre ; les threads daemon meurent à la
        # sortie du process et l'OS libère les ports. Déconnexion propre seulement
        # si aucun run n'est actif.
        if not self._busy:
            for d in (self.wav, self.aps, self.accel):
                try:
                    if d:
                        d.disconnect()
                except Exception:
                    pass
            try:
                if self.unit:
                    self.unit.close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    ThreeAxisApp().mainloop()
