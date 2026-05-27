"""
Interface graphique pour le banc de test ADS1285 Automation.

Permet de configurer tous les appareils (ADS1285, Wavetek, APS, accelerometre),
d'effectuer des acquisitions unitaires ou des balayages frequentiels,
et de visualiser les donnees dans des graphiques.

Usage :
    python gui.py
"""

import os
import sys
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import config.config_manager as _cfg_mgr
from config.settings import (
    ADS1285_BRIDGE_PORT, ADS1285_SAMPLE_RATE, ADS1285_NUM_SAMPLES,
    WAVETEK_PORT, WAVETEK_BAUD,
    APS_CONTROLLER_VERTICAL_PORT, APS_CONTROLLER_HORIZONTAL_PORT,
    APS125_GAIN_VERTICAL, APS125_GAIN_HORIZONTAL,
    APS125_CURRENT_LIMIT_VERTICAL, APS125_CURRENT_LIMIT_HORIZONTAL,
    NI_DEVICE_NAME, NI_AI_CHANNELS, NI_SAMPLE_RATE, NI_SAMPLES_PER_CHANNEL,
    NI_REF_CHANNEL_VERTICAL, NI_REF_CHANNEL_HORIZONTAL,
    SHAKER_ENVELOPE_FRACTION, SHAKER_ACCEL_CAP_G, SHAKER_GEOPHONE,
    DATA_OUTPUT_DIR,
)
from constants import CAL_DAILY_FREQS_HZ, CAL_DAILY_TOL_DB, CAL_CROSS_AXIS_MAX_PCT
from equipment.ads1285 import ADS1285
from equipment.wavetek import Wavetek39A
from equipment.aps import APSController
from equipment.testbench import TestBench, TestBenchAborted

# Dossier des references H_banc (vérification quotidienne)
_REF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference")
try:
    from equipment.accelerometer import Accelerometer
    _HAS_NIDAQMX = True
except ImportError:
    _HAS_NIDAQMX = False
    Accelerometer = None


# Modeles de geophones candidats a la calibration
GEOPHONE_MODELS = [
    "HG-5VHS",
    "HG-6 HB",
    "HG-6XT UB",
    "HG-2 U",
    "VAS-200 (V)",
    "VAS-H-200",
    "ST-2A (V)",
    "ST-2A (H)",
]


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def compute_fft(samples, sample_rate):
    """Retourne (frequences_hz, magnitudes_dB) sans le bin DC."""
    arr = np.array(samples, dtype=np.float64)
    arr -= arr.mean()
    window = np.hanning(len(arr))
    arr *= window
    spectrum = np.fft.rfft(arr)
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / sample_rate)
    magnitude = np.abs(spectrum) * 2.0 / len(arr)
    magnitude_db = 20 * np.log10(magnitude + 1e-12)
    return freqs[1:], magnitude_db[1:]


# ---------------------------------------------------------------------------
# WorkerThread — execute une tache en arriere-plan
# ---------------------------------------------------------------------------

class WorkerThread(threading.Thread):
    """Execute *target_fn* dans un thread daemon, poste le resultat via root.after()."""

    def __init__(self, app, target_fn, callback_ok, callback_err, *args):
        super().__init__(daemon=True)
        self._app = app
        self._fn = target_fn
        self._args = args
        self._cb_ok = callback_ok
        self._cb_err = callback_err

    def run(self):
        try:
            result = self._fn(*self._args)
            self._app.after(0, self._cb_ok, result)
        except Exception as exc:
            self._app.after(0, self._cb_err, exc)


# ---------------------------------------------------------------------------
# DeviceManager — gere le cycle de vie des equipements
# ---------------------------------------------------------------------------

class DeviceManager:
    """Instancie, connecte et deconnecte les equipements."""

    DEVICE_NAMES = [
        "ads1285", "wavetek",
        "aps_ctrl_v", "aps_ctrl_h",
        "accel",
    ]

    def __init__(self):
        self.instances = {n: None for n in self.DEVICE_NAMES}
        self.connected = {n: False for n in self.DEVICE_NAMES}

    # --- connexion individuelle ---

    def connect_ads1285(self, port, sample_rate, num_samples):
        dev = ADS1285(port=port, sample_rate=sample_rate, num_samples=num_samples)
        dev.connect()
        self.instances["ads1285"] = dev
        self.connected["ads1285"] = True

    def disconnect_ads1285(self):
        dev = self.instances.get("ads1285")
        if dev:
            dev.disconnect()
        self.instances["ads1285"] = None
        self.connected["ads1285"] = False

    def connect_wavetek(self, port, baud):
        dev = Wavetek39A(port=port, baud=baud)
        dev.connect()
        self.instances["wavetek"] = dev
        self.connected["wavetek"] = True

    def disconnect_wavetek(self):
        dev = self.instances.get("wavetek")
        if dev:
            dev.disconnect()
        self.instances["wavetek"] = None
        self.connected["wavetek"] = False

    def connect_aps_ctrl(self, axis, port):
        key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        dev = APSController(axis=axis, port=port)
        dev.connect()
        self.instances[key] = dev
        self.connected[key] = True

    def disconnect_aps_ctrl(self, axis):
        key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        dev = self.instances.get(key)
        if dev:
            dev.disconnect()
        self.instances[key] = None
        self.connected[key] = False

    def connect_accel(self, device, channels, sample_rate, samples_per_channel):
        if not _HAS_NIDAQMX:
            raise RuntimeError("Module nidaqmx non disponible "
                               "(installez NI-DAQmx + pip install nidaqmx)")
        dev = Accelerometer(device=device, channels=channels,
                            sample_rate=sample_rate,
                            samples_per_channel=samples_per_channel)
        dev.connect()
        self.instances["accel"] = dev
        self.connected["accel"] = True

    def disconnect_accel(self):
        dev = self.instances.get("accel")
        if dev:
            dev.disconnect()
        self.instances["accel"] = None
        self.connected["accel"] = False

    def disconnect_all(self):
        for name in self.DEVICE_NAMES:
            dev = self.instances.get(name)
            if dev:
                try:
                    dev.disconnect()
                except Exception:
                    pass
            self.instances[name] = None
            self.connected[name] = False

    def make_testbench(self, axis: str,
                       fraction: float | None = None,
                       accel_cap_g: float | None = None) -> TestBench:
        """Construit un TestBench a partir des instruments connectes.

        Wavetek + APS (axe actif) + accelerometre sont requis ; l'ADS1285
        (geophone) est optionnel (sensibilite calculee seulement si present).
        Leve RuntimeError en listant ce qui manque.
        """
        missing = []
        wav = self.instances.get("wavetek")
        if not (wav and self.connected["wavetek"]):
            missing.append("Wavetek")
        accel = self.instances.get("accel")
        if not (accel and self.connected["accel"]):
            missing.append("Accelerometre")
        ctrl_key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        aps = self.instances.get(ctrl_key)
        if not (aps and self.connected[ctrl_key]):
            missing.append(f"APS Ctrl {axis}")
        if missing:
            raise RuntimeError("Calibration impossible — non connecte : "
                               + ", ".join(missing))

        ads = self.instances.get("ads1285") if self.connected["ads1285"] else None
        # Canal de l'accéléromètre de référence selon l'axe (un par axe)
        ref_channel = (NI_REF_CHANNEL_VERTICAL if axis == "vertical"
                       else NI_REF_CHANNEL_HORIZONTAL)
        kw = {"ref_channel": ref_channel}
        if fraction is not None:
            kw["envelope_fraction"] = fraction
        if accel_cap_g is not None:
            kw["accel_cap_g"] = accel_cap_g
        return TestBench(wav, aps, accel, ads, **kw)


# ---------------------------------------------------------------------------
# Panneau gauche scrollable
# ---------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    """Frame avec scrollbar verticale interne."""

    def __init__(self, parent, width=300, **kw):
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, width=width, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self, orient="vertical",
                                         command=self._canvas.yview)
        self.inner = ttk.Frame(self._canvas)
        self.inner.bind("<Configure>",
                        lambda _: self._canvas.configure(
                            scrollregion=self._canvas.bbox("all")))
        self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _bind_mousewheel(self, _):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

class Application(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ADS1285 Automation")
        self.geometry("1400x850")
        self.minsize(1100, 700)

        self._dm = DeviceManager()
        self._busy = False
        self._stop_event = threading.Event()

        # Donnees d'acquisition
        self._last_adc = None          # list[int]
        self._last_accel = None        # np.ndarray | None
        self._last_rate = ADS1285_SAMPLE_RATE
        # Resultats stockes PAR AXE (2 chaines shaker independantes V/H)
        self._sweep_results = {"vertical": {}, "horizontal": {}}  # {axe: {freq: res}}
        self._bench_results = {"vertical": {}, "horizontal": {}}  # {axe: {freq: res}}
        self._linearity_results = {"vertical": [], "horizontal": []}  # {axe: [entry]}
        self._cross_results = {}       # {freq: entry} sensibilité transversale
        self._noise_floor_g = {"vertical": None, "horizontal": None}  # g RMS par axe
        # Valeurs des knobs APS 125 saisies par l'usager (ampli manuel, par axe)
        self._aps125_gains = {"vertical": "", "horizontal": ""}
        self._aps125_climits = {"vertical": "", "horizontal": ""}

        # Variables tkinter
        self._vars = {}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ===================================================================
    # Construction de l'interface
    # ===================================================================

    def _build_ui(self):
        # PanedWindow horizontal : gauche (config) | droite (graphiques)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Panneau gauche (scrollable) ---
        self._left = ScrollableFrame(paned, width=310)
        paned.add(self._left, weight=0)
        self._build_left_panel()

        # --- Panneau droit ---
        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self._build_right_panel(right)

        # --- Barre d'actions ---
        self._build_action_bar()

        # --- Barre de statut ---
        self._build_status_bar()

    # ---------------------------------------------------------------
    # Panneau gauche — sections appareils
    # ---------------------------------------------------------------

    def _build_left_panel(self):
        parent = self._left.inner

        # ADS1285
        self._build_ads1285_section(parent)
        # Wavetek
        self._build_wavetek_section(parent)
        # APS (sélecteur d'axe commun + Contrôleur + Amplificateur)
        self._build_aps_section(parent)
        # Accelerometre
        self._build_accel_section(parent)
        # Calibration banc (sweep géophone)
        self._build_calibration_section(parent)

    def _build_calibration_section(self, parent):
        lf = ttk.LabelFrame(parent, text="  Calibration banc")
        lf.pack(fill="x", padx=4, pady=3)
        f = ttk.Frame(lf)
        f.pack(fill="x", padx=5, pady=5)
        f.columnconfigure(1, weight=1)

        _geo_default = SHAKER_GEOPHONE if SHAKER_GEOPHONE in GEOPHONE_MODELS \
            else GEOPHONE_MODELS[0]
        self._row(f, "Géophone :",
                  self._make_var("cal_geophone", _geo_default), 0,
                  combo_values=GEOPHONE_MODELS, width=14)
        self._row(f, "Fraction env. :",
                  self._make_var("cal_fraction", SHAKER_ENVELOPE_FRACTION), 1)
        self._row(f, "Plafond (g) :",
                  self._make_var("cal_cap", SHAKER_ACCEL_CAP_G), 2)
        self._row(f, "Bruit (s) :",
                  self._make_var("cal_noise_s", "60"), 3)

        bf = ttk.Frame(lf)
        bf.pack(fill="x", padx=5, pady=(0, 3))
        self._btn_cal_zero = ttk.Button(bf, text="Centrage ZER", width=12,
                                        command=self._center_zero)
        self._btn_cal_zero.pack(side="left", padx=(0, 4))
        self._btn_noise = ttk.Button(bf, text="Plancher bruit", width=13,
                                     command=self._measure_noise_floor)
        self._btn_noise.pack(side="left")

        bf2 = ttk.Frame(lf)
        bf2.pack(fill="x", padx=5, pady=(0, 3))
        self._btn_bench = ttk.Button(bf2, text="Transfert banc", width=12,
                                     command=self._measure_bench_transfer)
        self._btn_bench.pack(side="left", padx=(0, 4))
        self._btn_set_ref = ttk.Button(bf2, text="Définir réf.", width=13,
                                       command=self._set_reference_hbanc)
        self._btn_set_ref.pack(side="left")

        bf3 = ttk.Frame(lf)
        bf3.pack(fill="x", padx=5, pady=(0, 3))
        self._btn_linearity = ttk.Button(bf3, text="Linéarité", width=12,
                                         command=self._do_linearity)
        self._btn_linearity.pack(side="left", padx=(0, 4))
        self._btn_daily = ttk.Button(bf3, text="Vérif. quotid.", width=13,
                                     command=self._do_daily_verification)
        self._btn_daily.pack(side="left")

        bf4 = ttk.Frame(lf)
        bf4.pack(fill="x", padx=5, pady=(0, 3))
        self._btn_campaign = ttk.Button(bf4, text="Campagne 2 axes auto (V+H)",
                                        command=self._do_campaign)
        self._btn_campaign.pack(side="left")

        bf5 = ttk.Frame(lf)
        bf5.pack(fill="x", padx=5, pady=(0, 3))
        self._btn_cross = ttk.Button(bf5, text="Transversale (cross-axis)",
                                     command=self._do_cross_axis)
        self._btn_cross.pack(side="left")

        self._lbl_noise_floor = ttk.Label(lf, text="", font=("", 8))
        self._lbl_noise_floor.pack(anchor="w", padx=6)
        ttk.Label(lf, text="(Balayage = sweep calibration géophone, axe courant)",
                  font=("", 8)).pack(anchor="w", padx=6, pady=(0, 4))

    def _make_var(self, key, default=""):
        var = tk.StringVar(value=str(default))
        self._vars[key] = var
        return var

    def _row(self, parent, label_text, var, row, combo_values=None, width=12):
        ttk.Label(parent, text=label_text).grid(row=row, column=0,
                                                 sticky="w", padx=2, pady=2)
        if combo_values:
            w = ttk.Combobox(parent, textvariable=var, values=combo_values,
                             width=width, state="readonly")
        else:
            w = ttk.Entry(parent, textvariable=var, width=width + 2)
        w.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        return w

    # --- ADS1285 ---

    def _build_ads1285_section(self, parent):
        lf = ttk.LabelFrame(parent, text="  ADS1285 EVM")
        lf.pack(fill="x", padx=4, pady=3)
        f = ttk.Frame(lf)
        f.pack(fill="x", padx=5, pady=5)
        f.columnconfigure(1, weight=1)

        self._row(f, "Port bridge :", self._make_var("ads_port", ADS1285_BRIDGE_PORT), 0)
        self._row(f, "Taux (SPS) :", self._make_var("ads_rate", ADS1285_SAMPLE_RATE), 1,
                  combo_values=["250", "500", "1000", "2000", "4000"])
        self._row(f, "Nb echantillons :", self._make_var("ads_count", ADS1285_NUM_SAMPLES), 2,
                  combo_values=["256", "512", "1024", "2048", "4096", "8192"])
        self._row(f, "Mode acq. :", self._make_var("ads_acq_mode", "PSM"), 3,
                  combo_values=["PSM", "ARM"])

        bf = ttk.Frame(lf)
        bf.pack(fill="x", padx=5, pady=(0, 5))
        self._btn_ads_connect = ttk.Button(bf, text="Connecter",
                                            command=self._toggle_ads1285)
        self._btn_ads_connect.pack(side="left", padx=(0, 5))
        self._btn_ads_test = ttk.Button(bf, text="Tester ADC",
                                         command=self._test_ads1285_adc,
                                         state="disabled")
        self._btn_ads_test.pack(side="left")
        self._lbl_ads_adc = ttk.Label(bf, text="", width=14)
        self._lbl_ads_adc.pack(side="left", padx=(4, 0))

    # --- Wavetek ---

    def _build_wavetek_section(self, parent):
        lf = ttk.LabelFrame(parent, text="  Wavetek 39A")
        lf.pack(fill="x", padx=4, pady=3)
        f = ttk.Frame(lf)
        f.pack(fill="x", padx=5, pady=5)
        f.columnconfigure(1, weight=1)

        self._row(f, "Port :", self._make_var("wav_port", WAVETEK_PORT), 0)
        self._row(f, "Forme d'onde :", self._make_var("wav_wave", "sine"), 1,
                  combo_values=["sine", "square", "triangle", "ramp",
                                "cosine", "pulse", "dc"])
        self._row(f, "Frequence (Hz) :", self._make_var("wav_freq", "10.0"), 2)
        self._row(f, "Amplitude (Vpp) :", self._make_var("wav_ampl", "1.0"), 3)
        self._row(f, "Offset (V) :", self._make_var("wav_offset", "0.0"), 4)

        bf = ttk.Frame(lf)
        bf.pack(fill="x", padx=5, pady=(0, 5))
        self._btn_wav_connect = ttk.Button(bf, text="Connecter",
                                            command=self._toggle_wavetek)
        self._btn_wav_connect.pack(side="left", padx=(0, 5))
        self._btn_wav_output = ttk.Button(bf, text="Sortie ON",
                                           command=self._toggle_wavetek_output,
                                           state="disabled")
        self._btn_wav_output.pack(side="left", padx=(0, 5))
        self._btn_wav_apply = ttk.Button(bf, text="Appliquer",
                                          command=self._apply_wavetek,
                                          state="disabled")
        self._btn_wav_apply.pack(side="left")
        self._wav_output_on = False

    # --- APS (sélecteur commun + Contrôleur + Amplificateur) ---

    def _build_aps_section(self, parent):
        # Données par axe
        self._aps_ctrl_ports = {
            "vertical":   APS_CONTROLLER_VERTICAL_PORT,
            "horizontal": APS_CONTROLLER_HORIZONTAL_PORT,
        }
        self._aps_ctrl_positions = {"vertical": "0.0", "horizontal": "0.0"}
        # Knobs APS 125 (manuels) restaurés depuis la config
        self._aps125_gains = {
            "vertical":   APS125_GAIN_VERTICAL,
            "horizontal": APS125_GAIN_HORIZONTAL,
        }
        self._aps125_climits = {
            "vertical":   APS125_CURRENT_LIMIT_VERTICAL,
            "horizontal": APS125_CURRENT_LIMIT_HORIZONTAL,
        }

        outer = ttk.LabelFrame(parent, text="  APS — Table de vibration")
        outer.pack(fill="x", padx=4, pady=3)

        # ── Sélecteur d'axe (partagé Ctrl + Amp) ──
        sel = ttk.Frame(outer)
        sel.pack(fill="x", padx=5, pady=(6, 4))
        ttk.Label(sel, text="Axe :").pack(side="left", padx=(0, 8))
        self._vars["aps_axis"] = tk.StringVar(value="vertical")
        for val, txt in [("vertical", "Vertical"), ("horizontal", "Horizontal")]:
            ttk.Radiobutton(sel, text=txt, variable=self._vars["aps_axis"],
                            value=val,
                            command=self._on_aps_axis_change).pack(
                side="left", padx=6)

        # Indicateurs de connexion V/H pour ctrl et amp
        ind = ttk.Frame(outer)
        ind.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(ind, text="Ctrl :").pack(side="left")
        self._lbl_ctrl_v_ind = ttk.Label(ind, text="● V", foreground="gray")
        self._lbl_ctrl_v_ind.pack(side="left", padx=(4, 8))
        self._lbl_ctrl_h_ind = ttk.Label(ind, text="● H", foreground="gray")
        self._lbl_ctrl_h_ind.pack(side="left")

        ttk.Separator(outer, orient="horizontal").pack(fill="x", padx=5, pady=3)

        # ── Contrôleur ──
        ttk.Label(outer, text="Contrôleur (APS 0109)",
                  font=("", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        fc = ttk.Frame(outer)
        fc.pack(fill="x", padx=8, pady=3)
        fc.columnconfigure(1, weight=1)
        self._row(fc, "Port :",
                  self._make_var("aps_ctrl_port", APS_CONTROLLER_VERTICAL_PORT), 0)
        self._row(fc, "Position (mm) :",
                  self._make_var("aps_ctrl_pos", "0.0"), 1)
        bfc = ttk.Frame(outer)
        bfc.pack(fill="x", padx=8, pady=(0, 6))
        self._btn_aps_ctrl_connect = ttk.Button(bfc, text="Connecter",
                                                 command=self._toggle_aps_ctrl_active)
        self._btn_aps_ctrl_connect.pack(side="left", padx=(0, 5))
        self._btn_aps_ctrl_pos = ttk.Button(bfc, text="Positionner",
                                             state="disabled",
                                             command=self._set_aps_ctrl_active)
        self._btn_aps_ctrl_pos.pack(side="left")

        # ── Amplificateur APS 125 (manuel — on enregistre la valeur du knob) ──
        ttk.Separator(outer, orient="horizontal").pack(fill="x", padx=5, pady=3)
        ttk.Label(outer, text="Amplificateur (APS 125 — manuel)",
                  font=("", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        fa = ttk.Frame(outer)
        fa.pack(fill="x", padx=8, pady=(3, 6))
        fa.columnconfigure(1, weight=1)
        self._row(fa, "Gain (dB) :",
                  self._make_var("aps125_gain", self._aps125_gains["vertical"]), 0)
        self._row(fa, "Limite courant (A RMS) :",
                  self._make_var("aps125_climit", self._aps125_climits["vertical"]), 1)
        ttk.Label(outer, text="(knobs saisis à la main, tracés avec l'étalonnage)",
                  font=("", 8)).pack(anchor="w", padx=8, pady=(0, 4))

    def _on_aps_axis_change(self):
        """Permute les champs Ctrl + gain ampli vers le nouvel axe."""
        prev = getattr(self, "_aps_prev_axis", None)
        if prev:
            self._aps_ctrl_ports[prev]    = self._vars["aps_ctrl_port"].get()
            self._aps_ctrl_positions[prev] = self._vars["aps_ctrl_pos"].get()
            self._aps125_gains[prev]       = self._vars["aps125_gain"].get()
            self._aps125_climits[prev]     = self._vars["aps125_climit"].get()

        axis = self._vars["aps_axis"].get()
        self._aps_prev_axis = axis
        self._vars["aps_ctrl_port"].set(self._aps_ctrl_ports[axis])
        self._vars["aps_ctrl_pos"].set(self._aps_ctrl_positions[axis])
        self._vars["aps125_gain"].set(self._aps125_gains[axis])
        self._vars["aps125_climit"].set(self._aps125_climits[axis])

        # Mettre a jour les boutons selon l'etat de connexion de cet axe
        ctrl_key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        ctrl_conn = self._dm.connected.get(ctrl_key, False)
        self._btn_aps_ctrl_connect.configure(
            text="Deconnecter" if ctrl_conn else "Connecter")
        self._btn_aps_ctrl_pos.configure(
            state="normal" if ctrl_conn else "disabled")

    def _toggle_aps_ctrl_active(self):
        self._toggle_aps_ctrl(self._vars["aps_axis"].get())

    def _set_aps_ctrl_active(self):
        self._set_aps_position(self._vars["aps_axis"].get())

    # --- Accelerometre ---

    def _build_accel_section(self, parent):
        lf = ttk.LabelFrame(parent, text="  Accelerometre NI")
        lf.pack(fill="x", padx=4, pady=3)
        f = ttk.Frame(lf)
        f.pack(fill="x", padx=5, pady=5)
        f.columnconfigure(1, weight=1)

        self._row(f, "Device :", self._make_var("accel_dev", NI_DEVICE_NAME), 0)
        self._row(f, "Canaux :", self._make_var("accel_ch", NI_AI_CHANNELS), 1)
        self._row(f, "Taux (Hz) :", self._make_var("accel_rate", NI_SAMPLE_RATE), 2)
        self._row(f, "Ech./canal :", self._make_var("accel_spc", NI_SAMPLES_PER_CHANNEL), 3)

        bf = ttk.Frame(lf)
        bf.pack(fill="x", padx=5, pady=(0, 5))
        self._btn_accel_connect = ttk.Button(bf, text="Connecter",
                                              command=self._toggle_accel)
        self._btn_accel_connect.pack(side="left")

    # ---------------------------------------------------------------
    # Panneau droit — graphiques matplotlib
    # ---------------------------------------------------------------

    def _build_right_panel(self, parent):
        self._notebook = ttk.Notebook(parent)
        self._notebook.pack(fill="both", expand=True)

        # Onglet Temporel
        tab_time = ttk.Frame(self._notebook)
        self._notebook.add(tab_time, text="  Temporel  ")
        self._fig_time = Figure(figsize=(8, 5), dpi=100)
        self._ax_adc = self._fig_time.add_subplot(211)
        self._ax_accel_t = self._fig_time.add_subplot(212)
        self._ax_adc.set_title("ADS1285 — Domaine temporel")
        self._ax_adc.set_xlabel("Temps (s)")
        self._ax_adc.set_ylabel("Valeur brute")
        self._ax_accel_t.set_title("Accelerometre")
        self._ax_accel_t.set_xlabel("Temps (s)")
        self._ax_accel_t.set_ylabel("Tension (V)")
        self._fig_time.tight_layout()
        self._canvas_time = FigureCanvasTkAgg(self._fig_time, master=tab_time)
        self._canvas_time.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_time = NavigationToolbar2Tk(self._canvas_time, tab_time)
        self._toolbar_time.update()

        # Onglet FFT
        tab_fft = ttk.Frame(self._notebook)
        self._notebook.add(tab_fft, text="  FFT  ")
        self._fig_fft = Figure(figsize=(8, 5), dpi=100)
        self._ax_fft_adc = self._fig_fft.add_subplot(211)
        self._ax_fft_accel = self._fig_fft.add_subplot(212)
        self._ax_fft_adc.set_title("FFT — ADS1285")
        self._ax_fft_adc.set_xlabel("Frequence (Hz)")
        self._ax_fft_adc.set_ylabel("Magnitude (dB)")
        self._ax_fft_accel.set_title("FFT — Accelerometre")
        self._ax_fft_accel.set_xlabel("Frequence (Hz)")
        self._ax_fft_accel.set_ylabel("Magnitude (dB)")
        self._fig_fft.tight_layout()
        self._canvas_fft = FigureCanvasTkAgg(self._fig_fft, master=tab_fft)
        self._canvas_fft.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_fft = NavigationToolbar2Tk(self._canvas_fft, tab_fft)
        self._toolbar_fft.update()

        # Onglet Balayage
        tab_sweep = ttk.Frame(self._notebook)
        self._notebook.add(tab_sweep, text="  Balayage  ")
        self._fig_sweep = Figure(figsize=(8, 5), dpi=100)
        self._ax_sweep = self._fig_sweep.add_subplot(111)
        self._ax_sweep.set_title("Sensibilite geophone vs frequence")
        self._ax_sweep.set_xlabel("Frequence (Hz)")
        self._ax_sweep.set_ylabel("Sensibilite (counts/g)")
        self._ax_sweep.set_xscale("log")
        self._ax_sweep.grid(True, which="both", linestyle="--", alpha=0.5)
        self._fig_sweep.tight_layout()
        self._canvas_sweep = FigureCanvasTkAgg(self._fig_sweep, master=tab_sweep)
        self._canvas_sweep.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_sweep = NavigationToolbar2Tk(self._canvas_sweep, tab_sweep)
        self._toolbar_sweep.update()

        # Onglet Transfert banc (H_banc)
        tab_bench = ttk.Frame(self._notebook)
        self._notebook.add(tab_bench, text="  Transfert banc  ")
        self._fig_bench = Figure(figsize=(8, 5), dpi=100)
        self._ax_bench = self._fig_bench.add_subplot(111)
        self._ax_bench.set_title("Fonction de transfert du banc H_banc(f)")
        self._ax_bench.set_xlabel("Frequence (Hz)")
        self._ax_bench.set_ylabel("H_banc (g/V)")
        self._ax_bench.set_xscale("log")
        self._ax_bench.grid(True, which="both", linestyle="--", alpha=0.5)
        self._fig_bench.tight_layout()
        self._canvas_bench = FigureCanvasTkAgg(self._fig_bench, master=tab_bench)
        self._canvas_bench.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_bench = NavigationToolbar2Tk(self._canvas_bench, tab_bench)
        self._toolbar_bench.update()

        # Onglet Linéarité
        tab_lin = ttk.Frame(self._notebook)
        self._notebook.add(tab_lin, text="  Linéarité  ")
        self._fig_lin = Figure(figsize=(8, 5), dpi=100)
        self._ax_lin = self._fig_lin.add_subplot(111)
        self._ax_lin.set_title("Linearite — sensibilite vs niveau d'excitation")
        self._ax_lin.set_xlabel("Acceleration excitation (g)")
        self._ax_lin.set_ylabel("Sensibilite (counts/g)")
        self._ax_lin.grid(True, linestyle="--", alpha=0.5)
        self._fig_lin.tight_layout()
        self._canvas_lin = FigureCanvasTkAgg(self._fig_lin, master=tab_lin)
        self._canvas_lin.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_lin = NavigationToolbar2Tk(self._canvas_lin, tab_lin)
        self._toolbar_lin.update()

        # Onglet Transversale (sensibilité transverse)
        tab_cross = ttk.Frame(self._notebook)
        self._notebook.add(tab_cross, text="  Transversale  ")
        self._fig_cross = Figure(figsize=(8, 5), dpi=100)
        self._ax_cross = self._fig_cross.add_subplot(111)
        self._ax_cross.set_title("Sensibilite transversale vs frequence")
        self._ax_cross.set_xlabel("Frequence (Hz)")
        self._ax_cross.set_ylabel("Transversale (%)")
        self._ax_cross.set_xscale("log")
        self._ax_cross.grid(True, which="both", linestyle="--", alpha=0.5)
        self._fig_cross.tight_layout()
        self._canvas_cross = FigureCanvasTkAgg(self._fig_cross, master=tab_cross)
        self._canvas_cross.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar_cross = NavigationToolbar2Tk(self._canvas_cross, tab_cross)
        self._toolbar_cross.update()

    # ---------------------------------------------------------------
    # Barre d'actions
    # ---------------------------------------------------------------

    def _build_action_bar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(2, 0))

        self._btn_connect_all = ttk.Button(bar, text="Connecter tout",
                                            command=self._connect_all)
        self._btn_connect_all.pack(side="left", padx=3)

        self._btn_acquire = ttk.Button(bar, text="Acquisition",
                                        command=self._do_acquire)
        self._btn_acquire.pack(side="left", padx=3)

        self._btn_sweep = ttk.Button(bar, text="Balayage",
                                      command=self._do_sweep)
        self._btn_sweep.pack(side="left", padx=3)

        self._btn_save = ttk.Button(bar, text="Sauvegarder",
                                     command=self._do_save)
        self._btn_save.pack(side="left", padx=3)

        self._btn_stop = ttk.Button(bar, text="Arreter",
                                     command=self._do_stop, state="disabled")
        self._btn_stop.pack(side="left", padx=3)

        # Parametres balayage (inline)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                    padx=8, pady=2)
        ttk.Label(bar, text="Frequences :").pack(side="left", padx=(0, 3))
        self._make_var("sweep_freqs", "1, 2, 5, 10, 20, 50, 100")
        e = ttk.Entry(bar, textvariable=self._vars["sweep_freqs"], width=30)
        e.pack(side="left", padx=(0, 5))
        ttk.Label(bar, text="Stab. (s) :").pack(side="left")
        self._make_var("sweep_stab", "2.0")
        ttk.Entry(bar, textvariable=self._vars["sweep_stab"], width=5).pack(
            side="left", padx=(0, 5))

    # ---------------------------------------------------------------
    # Barre de statut
    # ---------------------------------------------------------------

    def _build_status_bar(self):
        bar = ttk.Frame(self, relief="sunken")
        bar.pack(fill="x", padx=4, pady=(2, 4))

        self._status_indicators = {}
        labels = {
            "ads1285": "ADS1285",
            "wavetek": "Wavetek",
            "aps_ctrl_v": "Ctrl V",
            "aps_ctrl_h": "Ctrl H",
            "accel": "Accel",
        }
        for key, text in labels.items():
            lbl = ttk.Label(bar, text=f"\u25cf {text}", foreground="gray")
            lbl.pack(side="left", padx=6)
            self._status_indicators[key] = lbl

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                    padx=6, pady=2)
        self._progress = ttk.Progressbar(bar, length=160, mode="determinate")
        self._progress.pack(side="left", padx=4)
        self._status_label = ttk.Label(bar, text="Pret")
        self._status_label.pack(side="left", padx=6)

    def _update_indicator(self, key, connected):
        color = "green" if connected else "gray"
        self._status_indicators[key].configure(foreground=color)

    def _set_status(self, text):
        self._status_label.configure(text=text)

    def _set_busy(self, busy, allow_stop=False):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self._btn_connect_all, self._btn_acquire,
                    self._btn_sweep, self._btn_save, self._btn_cal_zero,
                    self._btn_noise, self._btn_bench, self._btn_set_ref,
                    self._btn_linearity, self._btn_daily, self._btn_campaign,
                    self._btn_cross):
            btn.configure(state=state)
        self._btn_stop.configure(state="normal" if (busy and allow_stop)
                                  else "disabled")
        # Le bouton "Tester ADC" suit l'etat de connexion quand on n'est pas occupe
        if busy:
            self._btn_ads_test.configure(state="disabled")
        else:
            self._btn_ads_test.configure(
                state="normal" if self._dm.connected["ads1285"] else "disabled")

    # ===================================================================
    # Connexion / deconnexion des appareils
    # ===================================================================

    def _toggle_ads1285(self):
        if self._dm.connected["ads1285"]:
            self._set_status("Deconnexion ADS1285...")
            self._set_busy(True)
            WorkerThread(self, self._dm.disconnect_ads1285,
                         lambda _: self._on_device_toggled("ads1285", False),
                         self._on_error).start()
        else:
            port = int(self._vars["ads_port"].get())
            rate = int(self._vars["ads_rate"].get())
            count = int(self._vars["ads_count"].get())
            self._set_status("Connexion ADS1285 — init FPGA/PSM (~15 s)...")
            self._set_busy(True)
            self._progress.configure(mode="indeterminate")
            self._progress.start(20)

            def _on_connected(_):
                self._progress.stop()
                self._progress.configure(mode="determinate", value=0)
                self._on_device_toggled("ads1285", True)

            def _on_conn_err(exc):
                self._progress.stop()
                self._progress.configure(mode="determinate", value=0)
                self._on_error(exc)

            WorkerThread(self, self._dm.connect_ads1285,
                         _on_connected, _on_conn_err,
                         port, rate, count).start()

    def _toggle_wavetek(self):
        if self._dm.connected["wavetek"]:
            self._set_busy(True)
            WorkerThread(self, self._dm.disconnect_wavetek,
                         lambda _: self._on_device_toggled("wavetek", False),
                         self._on_error).start()
        else:
            port = self._vars["wav_port"].get()
            baud = WAVETEK_BAUD
            self._set_status("Connexion Wavetek...")
            self._set_busy(True)
            WorkerThread(self, self._dm.connect_wavetek,
                         lambda _: self._on_device_toggled("wavetek", True),
                         self._on_error, port, baud).start()

    def _toggle_aps_ctrl(self, axis):
        key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        if self._dm.connected[key]:
            self._set_busy(True)
            WorkerThread(self, self._dm.disconnect_aps_ctrl,
                         lambda _, k=key: self._on_device_toggled(k, False),
                         self._on_error, axis).start()
        else:
            if self._vars["aps_axis"].get() == axis:
                port = self._vars["aps_ctrl_port"].get()
                self._aps_ctrl_ports[axis] = port
            else:
                port = self._aps_ctrl_ports[axis]
            self._set_status(f"Connexion APS Ctrl {axis}...")
            self._set_busy(True)
            WorkerThread(self, self._dm.connect_aps_ctrl,
                         lambda _, k=key: self._on_device_toggled(k, True),
                         self._on_error, axis, port).start()

    def _toggle_accel(self):
        if self._dm.connected["accel"]:
            self._set_busy(True)
            WorkerThread(self, self._dm.disconnect_accel,
                         lambda _: self._on_device_toggled("accel", False),
                         self._on_error).start()
        else:
            dev = self._vars["accel_dev"].get()
            ch = self._vars["accel_ch"].get()
            rate = int(self._vars["accel_rate"].get())
            spc = int(self._vars["accel_spc"].get())
            self._set_status("Connexion accelerometre...")
            self._set_busy(True)
            WorkerThread(self, self._dm.connect_accel,
                         lambda _: self._on_device_toggled("accel", True),
                         self._on_error, dev, ch, rate, spc).start()

    def _on_device_toggled(self, key, connected):
        self._dm.connected[key] = connected
        self._update_indicator(key, connected)
        self._set_busy(False)

        if key == "ads1285":
            self._btn_ads_connect.configure(
                text="Deconnecter" if connected else "Connecter")
            self._btn_ads_test.configure(
                state="normal" if connected else "disabled")
            if not connected:
                self._lbl_ads_adc.configure(text="")

        elif key == "wavetek":
            self._btn_wav_connect.configure(
                text="Deconnecter" if connected else "Connecter")
            state = "normal" if connected else "disabled"
            self._btn_wav_output.configure(state=state)
            self._btn_wav_apply.configure(state=state)

        elif key.startswith("aps_ctrl"):
            axis = "vertical" if key == "aps_ctrl_v" else "horizontal"
            lbl = self._lbl_ctrl_v_ind if axis == "vertical" else self._lbl_ctrl_h_ind
            lbl.configure(foreground="green" if connected else "gray")
            if self._vars["aps_axis"].get() == axis:
                self._btn_aps_ctrl_connect.configure(
                    text="Deconnecter" if connected else "Connecter")
                self._btn_aps_ctrl_pos.configure(
                    state="normal" if connected else "disabled")

        elif key == "accel":
            self._btn_accel_connect.configure(
                text="Deconnecter" if connected else "Connecter")

        self._set_status("Pret")

    def _on_error(self, exc):
        self._set_busy(False)
        self._set_status("Erreur")
        messagebox.showerror("Erreur", str(exc))

    # --- Test ADC single-shot ---

    def _test_ads1285_adc(self):
        """Lit un seul echantillon ADC via read_raw_adc (sans PSM, rapide)."""
        dev = self._dm.instances.get("ads1285")
        if not dev:
            return
        self._set_status("Lecture ADC single-shot...")
        self._btn_ads_test.configure(state="disabled")

        def _worker():
            return dev.read_raw_adc(0)

        def _on_done(value):
            self._btn_ads_test.configure(state="normal")
            self._lbl_ads_adc.configure(text=f"ADC={value}")
            self._set_status(f"ADC single-shot : {value}")

        def _on_err(exc):
            self._btn_ads_test.configure(state="normal")
            self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    # --- Connecter tout ---

    def _connect_all(self):
        self._set_busy(True)
        self._set_status("Connexion de tous les appareils...")

        def _worker():
            errors = []
            # ADS1285
            try:
                port = int(self._vars["ads_port"].get())
                rate = int(self._vars["ads_rate"].get())
                count = int(self._vars["ads_count"].get())
                self._dm.connect_ads1285(port, rate, count)
                self.after(0, self._update_indicator, "ads1285", True)
                self.after(0, self._btn_ads_connect.configure,
                           {"text": "Deconnecter"})
            except Exception as e:
                errors.append(f"ADS1285: {e}")
            # Wavetek
            try:
                self._dm.connect_wavetek(self._vars["wav_port"].get(),
                                         WAVETEK_BAUD)
                self.after(0, self._update_indicator, "wavetek", True)
                self.after(0, self._btn_wav_connect.configure,
                           {"text": "Deconnecter"})
                self.after(0, self._btn_wav_output.configure,
                           {"state": "normal"})
                self.after(0, self._btn_wav_apply.configure,
                           {"state": "normal"})
            except Exception as e:
                errors.append(f"Wavetek: {e}")
            # APS Controllers
            active_axis = self._vars["aps_axis"].get()
            self._aps_ctrl_ports[active_axis] = self._vars["aps_ctrl_port"].get()
            for axis, key in [("vertical", "aps_ctrl_v"),
                              ("horizontal", "aps_ctrl_h")]:
                try:
                    self._dm.connect_aps_ctrl(axis, self._aps_ctrl_ports[axis])
                    self.after(0, self._update_indicator, key, True)
                    lbl = (self._lbl_ctrl_v_ind if axis == "vertical"
                           else self._lbl_ctrl_h_ind)
                    self.after(0, lbl.configure, {"foreground": "green"})
                    if active_axis == axis:
                        self.after(0, self._btn_aps_ctrl_connect.configure,
                                   {"text": "Deconnecter"})
                        self.after(0, self._btn_aps_ctrl_pos.configure,
                                   {"state": "normal"})
                except Exception as e:
                    errors.append(f"APS Ctrl {axis}: {e}")
            # Accelerometre
            try:
                dev = self._vars["accel_dev"].get()
                ch = self._vars["accel_ch"].get()
                rate = int(self._vars["accel_rate"].get())
                spc = int(self._vars["accel_spc"].get())
                self._dm.connect_accel(dev, ch, rate, spc)
                self.after(0, self._update_indicator, "accel", True)
                self.after(0, self._btn_accel_connect.configure,
                           {"text": "Deconnecter"})
            except Exception as e:
                errors.append(f"Accelerometre: {e}")
            return errors

        def _on_done(errors):
            self._set_busy(False)
            if errors:
                self._set_status(f"{len(errors)} erreur(s) de connexion")
                messagebox.showwarning("Connexion partielle",
                                       "\n".join(errors))
            else:
                self._set_status("Tous les appareils connectes")

        WorkerThread(self, _worker, _on_done, self._on_error).start()

    # ===================================================================
    # Actions Wavetek / APS
    # ===================================================================

    def _toggle_wavetek_output(self):
        dev = self._dm.instances.get("wavetek")
        if not dev:
            return
        if self._wav_output_on:
            dev.disable_output()
            self._btn_wav_output.configure(text="Sortie ON")
            self._wav_output_on = False
        else:
            dev.enable_output()
            self._btn_wav_output.configure(text="Sortie OFF")
            self._wav_output_on = True

    def _apply_wavetek(self):
        dev = self._dm.instances.get("wavetek")
        if not dev:
            return
        try:
            dev.set_waveform(self._vars["wav_wave"].get())
            dev.set_frequency(float(self._vars["wav_freq"].get()))
            dev.set_amplitude(float(self._vars["wav_ampl"].get()))
            dev.set_offset(float(self._vars["wav_offset"].get()))
            self._set_status("Wavetek configure")
        except Exception as e:
            messagebox.showerror("Wavetek", str(e))

    def _set_aps_position(self, axis):
        key = "aps_ctrl_v" if axis == "vertical" else "aps_ctrl_h"
        dev = self._dm.instances.get(key)
        if not dev:
            return
        try:
            pos = float(self._vars["aps_ctrl_pos"].get())
            self._aps_ctrl_positions[axis] = str(pos)
            dev.set_position(pos)
            self._set_status(f"APS Ctrl {axis} -> {pos} mm")
        except Exception as e:
            messagebox.showerror("APS", str(e))

    # ===================================================================
    # Acquisition unitaire
    # ===================================================================

    def _do_acquire(self):
        if not self._dm.connected["ads1285"]:
            messagebox.showwarning("Acquisition",
                                   "ADS1285 non connecte.")
            return
        rate = int(self._vars["ads_rate"].get())
        count = int(self._vars["ads_count"].get())
        self._last_rate = rate
        self._set_busy(True)
        self._set_status(f"Acquisition {count} ech. @ {rate} SPS...")
        self._progress.configure(mode="indeterminate")
        self._progress.start(20)

        acq_mode = self._vars["ads_acq_mode"].get()

        def _worker():
            dev = self._dm.instances["ads1285"]
            if acq_mode == "ARM":
                adc_data = dev.acquire_arm(count, rate)
            else:
                adc_data = dev.acquire(count, rate)
            accel_data = None
            if self._dm.connected.get("accel") and self._dm.instances.get("accel"):
                accel_data = self._dm.instances["accel"].acquire()
            return adc_data, accel_data

        def _on_done(result):
            adc_data, accel_data = result
            self._last_adc = adc_data
            self._last_accel = accel_data
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)
            self._set_busy(False)
            self._set_status(f"{len(adc_data)} echantillons acquis")
            self._update_time_plot()
            self._update_fft_plot()
            self._notebook.select(0)  # aller sur l'onglet Temporel

        def _on_err(exc):
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)
            self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    # ===================================================================
    # Balayage frequentiel
    # ===================================================================

    def _aps125_gain_for(self, axis: str) -> str:
        """Gain APS 125 d'un axe — valeur live pour l'axe actif, sinon le dict."""
        if axis == self._vars["aps_axis"].get():
            return self._vars["aps125_gain"].get()
        return self._aps125_gains.get(axis, "")

    def _aps125_climit_for(self, axis: str) -> str:
        """Limite courant APS 125 d'un axe (live pour l'axe actif, sinon dict)."""
        if axis == self._vars["aps_axis"].get():
            return self._vars["aps125_climit"].get()
        return self._aps125_climits.get(axis, "")

    def _do_sweep(self):
        """Sweep de calibration géophone piloté par le TestBench (banc complet)."""
        axis = self._vars["aps_axis"].get()
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            bench = self._dm.make_testbench(axis, fraction=fraction,
                                            accel_cap_g=cap)
        except (ValueError, RuntimeError) as e:
            messagebox.showwarning("Calibration", str(e))
            return

        try:
            freqs = [float(f.strip())
                     for f in self._vars["sweep_freqs"].get().split(",")]
        except ValueError:
            messagebox.showerror("Calibration", "Fréquences invalides.")
            return

        rate = int(self._vars["ads_rate"].get())
        count = int(self._vars["ads_count"].get())
        self._last_rate = rate
        self._sweep_results[axis] = {}        # n'écrase que l'axe courant
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._progress.configure(mode="determinate", maximum=len(freqs), value=0)
        self._notebook.select(2)  # onglet Balayage

        bench.set_stop_event(self._stop_event)
        bench.set_logger(lambda m: self.after(0, self._set_status, m))

        def _worker():
            return bench.calibration_sweep(
                freqs,
                geophone_count=count,
                geophone_rate=rate,
                on_point=lambda res: self.after(0, self._on_sweep_point, axis, res),
            )

        def _on_done(results):
            self._set_busy(False)
            n_ok = sum(1 for r in results if not r.get("skipped"))
            self._set_status(f"Calibration {axis} terminée — {n_ok}/{len(results)} points")

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Calibration interrompue (sécurité)")
                messagebox.showwarning("Calibration", str(exc))
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    _AXIS_STYLE = {
        "vertical":   ("tab:blue", "o-", "V"),
        "horizontal": ("tab:red", "s-", "H"),
    }

    def _on_sweep_point(self, axis: str, res: dict):
        freq = res["freq_hz"]
        # Tracer l'axe + les knobs ampli dans le résultat (traçabilité)
        res["axis"] = axis
        res["aps125_gain"] = self._aps125_gain_for(axis)
        res["aps125_current_limit"] = self._aps125_climit_for(axis)
        self._sweep_results[axis][freq] = res
        self._progress.configure(value=len(self._sweep_results[axis]))

        if res.get("skipped"):
            self._set_status(f"[{axis}] {freq} Hz ignoré — {res.get('note', '')}")
        else:
            self._set_status(
                f"[{axis}] {freq} Hz : {res['measured_g']:.4g} g, "
                f"STF {res['stiffness']}, dépl. {res['displacement_mm']:.2f} mm, "
                f"marge {res['safety_margin_mm']:.1f} mm")

        # Graphe sensibilité géophone (counts/g) vs fréquence — V et H superposés
        self._ax_sweep.clear()
        geophone = self._vars["cal_geophone"].get()
        self._ax_sweep.set_title(f"Sensibilite geophone vs frequence — {geophone}")
        self._ax_sweep.set_xlabel("Frequence (Hz)")
        self._ax_sweep.set_ylabel("Sensibilite (counts/g)")
        self._ax_sweep.set_xscale("log")
        self._ax_sweep.grid(True, which="both", linestyle="--", alpha=0.5)
        plotted = False
        for ax_name, results in self._sweep_results.items():
            fdone = sorted(f for f in results
                           if results[f].get("sensitivity_counts_per_g"))
            if not fdone:
                continue
            color, style, lbl = self._AXIS_STYLE[ax_name]
            sens = [results[f]["sensitivity_counts_per_g"] for f in fdone]
            self._ax_sweep.plot(fdone, sens, style, color=color, label=lbl)
            plotted = True
        if plotted:
            self._ax_sweep.legend()
        self._fig_sweep.tight_layout()
        self._canvas_sweep.draw_idle()

    def _center_zero(self):
        """Lance le centrage ZER statique du contrôleur APS de l'axe actif."""
        axis = self._vars["aps_axis"].get()
        try:
            bench = self._dm.make_testbench(axis)
        except RuntimeError as e:
            messagebox.showwarning("Centrage ZER", str(e))
            return
        bench.set_logger(lambda m: self.after(0, self._set_status, m))
        self._set_busy(True)

        def _worker():
            return bench.center_zero()

        def _on_done(zer):
            self._set_busy(False)
            self._set_status(f"Centrage ZER terminé (ZER={zer})")

        WorkerThread(self, _worker, _on_done, self._on_error).start()

    def _measure_noise_floor(self):
        """Mesure le plancher de bruit (accéléromètre, shaker à l'arrêt)."""
        if not (self._dm.connected.get("accel") and self._dm.instances.get("accel")):
            messagebox.showwarning("Plancher de bruit",
                                   "Accéléromètre non connecté.")
            return
        try:
            duration = float(self._vars["cal_noise_s"].get())
        except ValueError:
            messagebox.showerror("Plancher de bruit", "Durée invalide.")
            return
        accel = self._dm.instances["accel"]
        axis = self._vars["aps_axis"].get()
        ref_channel = (NI_REF_CHANNEL_VERTICAL if axis == "vertical"
                       else NI_REF_CHANNEL_HORIZONTAL)
        # Couper l'excitation si le Wavetek est connecté
        if self._dm.connected.get("wavetek") and self._dm.instances.get("wavetek"):
            try:
                self._dm.instances["wavetek"].disable_output()
            except Exception:
                pass
        self._set_busy(True)
        self._set_status(f"Plancher de bruit {axis} ({duration:.0f}s, shaker arrêté)...")
        self._progress.configure(mode="indeterminate")
        self._progress.start(20)

        def _worker():
            return accel.measure_noise_floor(duration, ref_channel=ref_channel)

        def _on_done(floor_g):
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)
            self._set_busy(False)
            self._noise_floor_g[axis] = floor_g       # mémorisé par axe
            self._lbl_noise_floor.configure(
                text=f"Plancher {axis[0].upper()} : {floor_g:.4g} g RMS")
            self._set_status(f"Plancher de bruit {axis} = {floor_g:.4g} g RMS "
                             "(sauvegardé avec la calibration)")

        def _on_err(exc):
            self._progress.stop()
            self._progress.configure(mode="determinate", value=0)
            self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    def _measure_bench_transfer(self):
        """Mesure la fonction de transfert du banc H_banc(f) (étape 1)."""
        axis = self._vars["aps_axis"].get()
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            bench = self._dm.make_testbench(axis, fraction=fraction,
                                            accel_cap_g=cap)
        except (ValueError, RuntimeError) as e:
            messagebox.showwarning("Transfert banc", str(e))
            return
        try:
            freqs = [float(f.strip())
                     for f in self._vars["sweep_freqs"].get().split(",")]
        except ValueError:
            messagebox.showerror("Transfert banc", "Fréquences invalides.")
            return

        self._bench_results[axis] = {}        # n'écrase que l'axe courant
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._progress.configure(mode="determinate", maximum=len(freqs), value=0)
        self._notebook.select(3)  # onglet Transfert banc

        bench.set_stop_event(self._stop_event)
        bench.set_logger(lambda m: self.after(0, self._set_status, m))

        def _worker():
            return bench.measure_bench_transfer(
                freqs,
                on_point=lambda res: self.after(0, self._on_bench_point, axis, res),
            )

        def _on_done(results):
            self._set_busy(False)
            n_ok = sum(1 for r in results if not r.get("skipped"))
            self._set_status(f"Transfert banc {axis} terminé — {n_ok}/{len(results)} points")

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Transfert banc interrompu (sécurité)")
                messagebox.showwarning("Transfert banc", str(exc))
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    def _on_bench_point(self, axis: str, res: dict):
        freq = res["freq_hz"]
        res["axis"] = axis
        res["aps125_gain"] = self._aps125_gain_for(axis)
        res["aps125_current_limit"] = self._aps125_climit_for(axis)
        self._bench_results[axis][freq] = res
        self._progress.configure(value=len(self._bench_results[axis]))

        if res.get("skipped"):
            self._set_status(f"[{axis}] {freq} Hz ignoré — {res.get('note', '')}")
        else:
            self._set_status(
                f"[{axis}] {freq} Hz : H_banc {res.get('h_bench_g_per_v', 0):.4g} g/V, "
                f"SNR {res.get('snr_db', 0):.1f} dB, THD {res.get('thd_percent', 0):.2f}%")

        self._ax_bench.clear()
        self._ax_bench.set_title("Fonction de transfert du banc H_banc(f)")
        self._ax_bench.set_xlabel("Frequence (Hz)")
        self._ax_bench.set_ylabel("H_banc (g/V)")
        self._ax_bench.set_xscale("log")
        self._ax_bench.grid(True, which="both", linestyle="--", alpha=0.5)
        plotted = False
        for ax_name, results in self._bench_results.items():
            fdone = sorted(f for f in results
                           if results[f].get("h_bench_g_per_v"))
            if not fdone:
                continue
            color, style, lbl = self._AXIS_STYLE[ax_name]
            hb = [results[f]["h_bench_g_per_v"] for f in fdone]
            self._ax_bench.plot(fdone, hb, style, color=color, label=lbl)
            plotted = True
        if plotted:
            self._ax_bench.legend()
        self._fig_bench.tight_layout()
        self._canvas_bench.draw_idle()

    # ---- Référence H_banc (vérification quotidienne) ----

    def _set_reference_hbanc(self):
        """Enregistre le H_banc courant de l'axe actif comme référence."""
        axis = self._vars["aps_axis"].get()
        results = self._bench_results[axis]
        ref = {str(f): results[f].get("h_bench_g_per_v")
               for f in results if results[f].get("h_bench_g_per_v")}
        if not ref:
            messagebox.showwarning("Référence H_banc",
                f"Aucune mesure H_banc pour l'axe {axis}.\n"
                "Lancez d'abord « Transfert banc ».")
            return
        os.makedirs(_REF_DIR, exist_ok=True)
        path = os.path.join(_REF_DIR, f"h_banc_{axis}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"axis": axis,
                       "date": datetime.now().isoformat(timespec="seconds"),
                       "aps125_gain": self._aps125_gain_for(axis),
                       "aps125_current_limit": self._aps125_climit_for(axis),
                       "h_banc_g_per_v": ref}, fh, indent=2)
        self._set_status(f"Référence H_banc {axis} enregistrée ({len(ref)} points)")

    def _load_reference_hbanc(self, axis):
        path = os.path.join(_REF_DIR, f"h_banc_{axis}.json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {float(k): v for k, v in data.get("h_banc_g_per_v", {}).items()}

    def _do_daily_verification(self):
        """Vérif. rapide H_banc à 1/10/50 Hz vs référence enregistrée."""
        axis = self._vars["aps_axis"].get()
        reference = self._load_reference_hbanc(axis)
        if not reference:
            messagebox.showwarning("Vérification quotidienne",
                f"Pas de référence H_banc pour l'axe {axis}.\n"
                "Faites « Transfert banc » puis « Définir réf. ».")
            return
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            bench = self._dm.make_testbench(axis, fraction=fraction, accel_cap_g=cap)
        except (ValueError, RuntimeError) as e:
            messagebox.showwarning("Vérification quotidienne", str(e))
            return
        daily = [f for f in CAL_DAILY_FREQS_HZ if f in reference]
        freqs = daily if daily else sorted(reference.keys())
        self._daily_results = []
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._progress.configure(mode="determinate", maximum=len(freqs), value=0)
        bench.set_stop_event(self._stop_event)
        bench.set_logger(lambda m: self.after(0, self._set_status, m))

        def _worker():
            return bench.daily_verification(
                reference, freqs=freqs,
                on_point=lambda res: self.after(0, self._on_daily_point, res))

        def _on_done(results):
            self._set_busy(False)
            valid = [r for r in results if not r.get("skipped")]
            ok = all(r.get("pass") for r in valid)
            worst = max((abs(r.get("deviation_db", 0)) for r in valid), default=0.0)
            self._set_status(f"Vérif. {axis} : écart max {worst:.2f} dB — "
                             + ("OK" if ok else "DÉRIVE"))
            if not ok:
                messagebox.showwarning("Vérification quotidienne",
                    f"Dérive détectée (écart max {worst:.2f} dB > "
                    f"{CAL_DAILY_TOL_DB} dB).\nRefaire l'étalonnage complet du banc.")

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Vérification interrompue")
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    def _on_daily_point(self, res: dict):
        self._daily_results.append(res)
        self._progress.configure(value=len(self._daily_results))
        if res.get("skipped"):
            self._set_status(f"{res['freq_hz']} Hz ignoré")
        else:
            self._set_status(
                f"{res['freq_hz']} Hz : {res.get('deviation_db', 0):+.2f} dB "
                f"({'OK' if res.get('pass') else 'DÉRIVE'})")

    # ---- Linéarité ----

    def _do_linearity(self):
        axis = self._vars["aps_axis"].get()
        if not self._dm.connected["ads1285"]:
            messagebox.showwarning("Linéarité", "ADS1285 (géophone) non connecté.")
            return
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            bench = self._dm.make_testbench(axis, fraction=fraction, accel_cap_g=cap)
            freqs = [float(f.strip())
                     for f in self._vars["sweep_freqs"].get().split(",")]
        except (ValueError, RuntimeError) as e:
            messagebox.showwarning("Linéarité", str(e))
            return
        rate = int(self._vars["ads_rate"].get())
        count = int(self._vars["ads_count"].get())
        self._linearity_results[axis] = []
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._progress.configure(mode="determinate", maximum=len(freqs), value=0)
        self._notebook.select(4)  # onglet Linéarité
        bench.set_stop_event(self._stop_event)
        bench.set_logger(lambda m: self.after(0, self._set_status, m))

        def _worker():
            return bench.measure_linearity(
                freqs, geophone_count=count, geophone_rate=rate,
                on_point=lambda e: self.after(0, self._on_linearity_point, axis, e))

        def _on_done(results):
            self._set_busy(False)
            ok = all(e["pass"] for e in results)
            worst = max((e["linearity_error_db"] for e in results), default=0.0)
            self._set_status(f"Linéarité {axis} : erreur max {worst:.2f} dB — "
                             + ("OK" if ok else "HORS TOL"))

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Linéarité interrompue (sécurité)")
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    def _on_linearity_point(self, axis: str, entry: dict):
        self._linearity_results[axis].append(entry)
        self._progress.configure(value=len(self._linearity_results[axis]))
        self._set_status(
            f"[{axis}] linéarité {entry['freq_hz']} Hz : "
            f"{entry['linearity_error_db']:.2f} dB "
            f"({'OK' if entry['pass'] else 'HORS TOL'})")

        self._ax_lin.clear()
        self._ax_lin.set_title("Linearite — sensibilite vs niveau d'excitation")
        self._ax_lin.set_xlabel("Acceleration excitation (g)")
        self._ax_lin.set_ylabel("Sensibilite (counts/g)")
        self._ax_lin.grid(True, linestyle="--", alpha=0.5)
        plotted = False
        for ax_name, entries in self._linearity_results.items():
            for e in entries:
                pts = [p for p in e["levels"]
                       if not p.get("skipped") and p.get("sensitivity_counts_per_g")]
                if not pts:
                    continue
                pts.sort(key=lambda p: p["measured_g"])
                xs = [p["measured_g"] for p in pts]
                ys = [p["sensitivity_counts_per_g"] for p in pts]
                self._ax_lin.plot(xs, ys, "o-",
                                  label=f"{ax_name[0].upper()} {e['freq_hz']}Hz")
                plotted = True
        if plotted:
            self._ax_lin.legend(fontsize=7)
        self._fig_lin.tight_layout()
        self._canvas_lin.draw_idle()

    # ---- Campagne 2 axes (automatique) ----

    def _do_campaign(self):
        """Campagne 2 axes automatique : étalonne V puis H sans intervention.

        Le splitter alimente les deux chaînes ; chaque axe a son accéléromètre
        de référence (canal NI dédié) et son contrôleur APS. Le logiciel bascule
        l'axe en interne — aucune manipulation physique entre les deux.
        Nécessite les deux contrôleurs APS connectés.
        """
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            freqs = [float(f.strip())
                     for f in self._vars["sweep_freqs"].get().split(",")]
        except ValueError:
            messagebox.showerror("Campagne", "Paramètres invalides.")
            return
        # Pré-valider que les deux axes sont disponibles
        try:
            self._dm.make_testbench("vertical", fraction=fraction, accel_cap_g=cap)
            self._dm.make_testbench("horizontal", fraction=fraction, accel_cap_g=cap)
        except RuntimeError as e:
            messagebox.showwarning("Campagne 2 axes", str(e))
            return

        rate = int(self._vars["ads_rate"].get())
        count = int(self._vars["ads_count"].get())
        self._last_rate = rate
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._notebook.select(2)

        def _set_axis_ui(ax):
            self._vars["aps_axis"].set(ax)
            self._on_aps_axis_change()

        def _worker():
            for ax in ("vertical", "horizontal"):
                if self._stop_event.is_set():
                    break
                self.after(0, _set_axis_ui, ax)
                bench = self._dm.make_testbench(ax, fraction=fraction,
                                                accel_cap_g=cap)
                bench.set_stop_event(self._stop_event)
                bench.set_logger(lambda m: self.after(0, self._set_status, m))
                bench.center_zero()
                self._sweep_results[ax] = {}
                self.after(0, lambda n=len(freqs): self._progress.configure(
                    mode="determinate", maximum=n, value=0))
                bench.calibration_sweep(
                    freqs, geophone_count=count, geophone_rate=rate,
                    on_point=lambda res, a=ax: self.after(0, self._on_sweep_point, a, res))
            return None

        def _on_done(_):
            self._set_busy(False)
            self._set_status("Campagne 2 axes terminée (V + H)")

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Campagne interrompue (sécurité)")
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    # ---- Sensibilité transversale (cross-axis) ----

    def _confirm_blocking(self, title: str, message: str) -> bool:
        """Affiche un askokcancel sur le thread principal et attend la réponse
        (appelé depuis un thread worker)."""
        evt = threading.Event()
        holder = {"ok": False}

        def ask():
            holder["ok"] = messagebox.askokcancel(title, message)
            evt.set()

        self.after(0, ask)
        evt.wait()
        return holder["ok"]

    def _do_cross_axis(self):
        """Sensibilité transversale en 2 phases : excitation le long de l'axe
        sensible, puis perpendiculaire (remontage du géophone). Mute l'axe
        non excité par STP du contrôleur."""
        main_axis = self._vars["aps_axis"].get()
        trans_axis = "horizontal" if main_axis == "vertical" else "vertical"
        if not self._dm.connected["ads1285"]:
            messagebox.showwarning("Transversale", "ADS1285 (géophone) requis.")
            return
        try:
            fraction = float(self._vars["cal_fraction"].get())
            cap = float(self._vars["cal_cap"].get())
            freqs = [float(f.strip())
                     for f in self._vars["sweep_freqs"].get().split(",")]
            bench_main = self._dm.make_testbench(main_axis, fraction=fraction,
                                                 accel_cap_g=cap)
            bench_trans = self._dm.make_testbench(trans_axis, fraction=fraction,
                                                  accel_cap_g=cap)
        except (ValueError, RuntimeError) as e:
            messagebox.showwarning("Transversale", str(e))
            return

        rate = int(self._vars["ads_rate"].get())
        count = int(self._vars["ads_count"].get())
        self._last_rate = rate
        self._cross_results = {}
        self._stop_event.clear()
        self._set_busy(True, allow_stop=True)
        self._notebook.select(5)  # onglet Transversale

        ctrl_key = lambda a: "aps_ctrl_v" if a == "vertical" else "aps_ctrl_h"
        main_ctrl = self._dm.instances[ctrl_key(main_axis)]
        trans_ctrl = self._dm.instances[ctrl_key(trans_axis)]

        def _sweep_sens(bench, mute_ctrl, label):
            self.after(0, self._set_status, f"Transversale — {label}")
            try:
                mute_ctrl.stop()         # STP : coupe l'AC de l'axe non mesuré
            except Exception:
                pass
            bench.set_stop_event(self._stop_event)
            bench.set_logger(lambda m: self.after(0, self._set_status, m))
            bench.center_zero()
            self.after(0, lambda n=len(freqs): self._progress.configure(
                mode="determinate", maximum=n, value=0))
            res = bench.calibration_sweep(freqs, geophone_count=count,
                                          geophone_rate=rate, on_point=lambda r: None)
            return {r["freq_hz"]: r.get("sensitivity_counts_per_g", 0.0)
                    for r in res if not r.get("skipped")}

        def _worker():
            # Phase 1 : excitation le long de l'axe sensible
            s_main = _sweep_sens(bench_main, trans_ctrl,
                                 f"phase 1 — axe principal {main_axis}")
            if self._stop_event.is_set():
                return None
            # Pause : remontage perpendiculaire
            if not self._confirm_blocking(
                    "Transversale — remontage",
                    f"Remontez le géophone sur le shaker {trans_axis},\n"
                    f"axe sensible PERPENDICULAIRE au mouvement.\n\n"
                    "OK pour mesurer la réponse transverse, Annuler pour arrêter."):
                return None
            # Phase 2 : excitation perpendiculaire
            s_trans = _sweep_sens(bench_trans, main_ctrl,
                                  f"phase 2 — axe transverse {trans_axis}")
            # Combinaison
            for f in sorted(set(s_main) & set(s_trans)):
                sm, st = s_main[f], s_trans[f]
                pct = (st / sm * 100.0) if sm > 1e-12 else 0.0
                entry = {"freq_hz": f, "s_main": sm, "s_trans": st,
                         "cross_axis_pct": pct,
                         "pass": pct <= CAL_CROSS_AXIS_MAX_PCT}
                self._cross_results[f] = entry
                self.after(0, self._on_cross_point, entry)
            return None

        def _on_done(_):
            self._set_busy(False)
            if self._cross_results:
                worst = max(e["cross_axis_pct"] for e in self._cross_results.values())
                ok = worst <= CAL_CROSS_AXIS_MAX_PCT
                self._set_status(f"Transversale : max {worst:.2f}% — "
                                 + ("OK" if ok else "HORS TOL"))
            else:
                self._set_status("Transversale : aucun point exploitable")

        def _on_err(exc):
            self._set_busy(False)
            if isinstance(exc, TestBenchAborted):
                self._set_status("Transversale interrompue (sécurité)")
            else:
                self._on_error(exc)

        WorkerThread(self, _worker, _on_done, _on_err).start()

    def _on_cross_point(self, entry: dict):
        self._set_status(
            f"{entry['freq_hz']} Hz : transversale {entry['cross_axis_pct']:.2f}% "
            f"({'OK' if entry['pass'] else 'HORS TOL'})")
        freqs_done = sorted(self._cross_results.keys())
        self._ax_cross.clear()
        self._ax_cross.set_title("Sensibilite transversale vs frequence")
        self._ax_cross.set_xlabel("Frequence (Hz)")
        self._ax_cross.set_ylabel("Transversale (%)")
        self._ax_cross.set_xscale("log")
        self._ax_cross.grid(True, which="both", linestyle="--", alpha=0.5)
        if freqs_done:
            pct = [self._cross_results[f]["cross_axis_pct"] for f in freqs_done]
            self._ax_cross.plot(freqs_done, pct, "o-", color="tab:purple")
            self._ax_cross.axhline(CAL_CROSS_AXIS_MAX_PCT, color="red",
                                   linestyle="--", alpha=0.7,
                                   label=f"seuil {CAL_CROSS_AXIS_MAX_PCT}%")
            self._ax_cross.legend()
        self._fig_cross.tight_layout()
        self._canvas_cross.draw_idle()

    def _do_stop(self):
        self._stop_event.set()
        self._set_status("Arret demande...")

    # ===================================================================
    # Mise a jour des graphiques
    # ===================================================================

    def _update_time_plot(self):
        data = self._last_adc
        if data is None:
            return
        rate = self._last_rate
        t = np.arange(len(data)) / rate

        self._ax_adc.clear()
        self._ax_adc.set_title("ADS1285 — Domaine temporel")
        self._ax_adc.set_xlabel("Temps (s)")
        self._ax_adc.set_ylabel("Valeur brute")
        self._ax_adc.plot(t, data, linewidth=0.5, color="tab:blue")
        self._ax_adc.grid(True, linestyle="--", alpha=0.4)

        self._ax_accel_t.clear()
        self._ax_accel_t.set_title("Accelerometre")
        self._ax_accel_t.set_xlabel("Temps (s)")
        self._ax_accel_t.set_ylabel("Tension (V)")
        if self._last_accel is not None:
            accel = self._last_accel
            accel_rate = int(self._vars["accel_rate"].get())
            n = accel.shape[1] if accel.ndim == 2 else len(accel)
            ta = np.arange(n) / accel_rate
            if accel.ndim == 2:
                for ch in range(accel.shape[0]):
                    self._ax_accel_t.plot(ta, accel[ch], linewidth=0.5,
                                          label=f"ch{ch}")
                self._ax_accel_t.legend(fontsize=8)
            else:
                self._ax_accel_t.plot(ta, accel, linewidth=0.5)
        self._ax_accel_t.grid(True, linestyle="--", alpha=0.4)

        self._fig_time.tight_layout()
        self._canvas_time.draw_idle()

    def _update_fft_plot(self):
        data = self._last_adc
        if data is None:
            return
        rate = self._last_rate
        freqs, mag = compute_fft(data, rate)

        self._ax_fft_adc.clear()
        self._ax_fft_adc.set_title("FFT — ADS1285")
        self._ax_fft_adc.set_xlabel("Frequence (Hz)")
        self._ax_fft_adc.set_ylabel("Magnitude (dB)")
        self._ax_fft_adc.plot(freqs, mag, linewidth=0.5, color="tab:blue")
        self._ax_fft_adc.grid(True, linestyle="--", alpha=0.4)

        self._ax_fft_accel.clear()
        self._ax_fft_accel.set_title("FFT — Accelerometre")
        self._ax_fft_accel.set_xlabel("Frequence (Hz)")
        self._ax_fft_accel.set_ylabel("Magnitude (dB)")
        if self._last_accel is not None:
            accel = self._last_accel
            accel_rate = int(self._vars["accel_rate"].get())
            if accel.ndim == 2:
                for ch in range(accel.shape[0]):
                    af, am = compute_fft(accel[ch], accel_rate)
                    self._ax_fft_accel.plot(af, am, linewidth=0.5,
                                            label=f"ch{ch}")
                self._ax_fft_accel.legend(fontsize=8)
            else:
                af, am = compute_fft(accel, accel_rate)
                self._ax_fft_accel.plot(af, am, linewidth=0.5)
        self._ax_fft_accel.grid(True, linestyle="--", alpha=0.4)

        self._fig_fft.tight_layout()
        self._canvas_fft.draw_idle()

    # ===================================================================
    # Sauvegarde
    # ===================================================================

    def _any_sweep_data(self) -> bool:
        return any(self._sweep_results[a] for a in self._sweep_results)

    def _do_save(self):
        if self._last_adc is None and not self._any_sweep_data():
            messagebox.showinfo("Sauvegarder",
                                "Aucune donnee a sauvegarder.")
            return

        path = filedialog.asksaveasfilename(
            initialdir=DATA_OUTPUT_DIR,
            initialfile=f"mesure_{datetime.now():%Y%m%d_%H%M%S}",
            filetypes=[("CSV", "*.csv"), ("NumPy NPZ", "*.npz")],
            defaultextension=".csv",
        )
        if not path:
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        if path.endswith(".npz"):
            self._save_npz(path)
        else:
            self._save_csv(path)

        self._set_status(f"Sauvegarde : {os.path.basename(path)}")

    # Colonnes du sweep de calibration (schéma TestBench.calibration_sweep)
    _SWEEP_COLUMNS = [
        "freq_hz", "target_g", "measured_g", "vpp", "stiffness",
        "displacement_mm", "safety_margin_mm",
        "snr_db", "thd_percent",
        "geophone_counts_peak", "sensitivity_counts_per_g",
        "skipped", "note",
    ]

    def _save_csv(self, path):
        rate = self._last_rate
        geophone = self._vars["cal_geophone"].get()
        if self._any_sweep_data():
            # Calibration géophone en CSV — une table, axe + knobs par ligne
            cols = (["axis", "aps125_gain", "aps125_current_limit"]
                    + self._SWEEP_COLUMNS)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# geophone: {geophone}\n")
                f.write(f"# date: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"# aps125_gain_vertical: {self._aps125_gain_for('vertical')}\n")
                f.write(f"# aps125_gain_horizontal: {self._aps125_gain_for('horizontal')}\n")
                f.write(f"# aps125_current_limit_vertical: {self._aps125_climit_for('vertical')}\n")
                f.write(f"# aps125_current_limit_horizontal: {self._aps125_climit_for('horizontal')}\n")
                f.write(f"# noise_floor_vertical_g_rms: {self._noise_floor_g['vertical']}\n")
                f.write(f"# noise_floor_horizontal_g_rms: {self._noise_floor_g['horizontal']}\n")
                f.write(",".join(cols) + "\n")
                for ax_name in ("vertical", "horizontal"):
                    results = self._sweep_results[ax_name]
                    for freq in sorted(results.keys()):
                        d = results[freq]
                        row = []
                        for col in cols:
                            val = d.get(col, "")
                            if isinstance(val, float):
                                row.append(f"{val:.6g}")
                            else:
                                row.append(str(val).replace(",", ";"))
                        f.write(",".join(row) + "\n")
        elif self._last_adc is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write("index,time_s,value\n")
                for i, val in enumerate(self._last_adc):
                    f.write(f"{i},{i/rate:.9f},{val}\n")

    def _save_npz(self, path):
        save_dict = {
            "geophone": np.array(self._vars["cal_geophone"].get()),
            "aps125_gain_vertical": np.array(self._aps125_gain_for("vertical")),
            "aps125_gain_horizontal": np.array(self._aps125_gain_for("horizontal")),
            "aps125_current_limit_vertical":
                np.array(self._aps125_climit_for("vertical")),
            "aps125_current_limit_horizontal":
                np.array(self._aps125_climit_for("horizontal")),
            "noise_floor_vertical_g_rms":
                np.array(self._noise_floor_g["vertical"]
                         if self._noise_floor_g["vertical"] is not None else np.nan),
            "noise_floor_horizontal_g_rms":
                np.array(self._noise_floor_g["horizontal"]
                         if self._noise_floor_g["horizontal"] is not None else np.nan),
        }
        if self._last_adc is not None:
            save_dict["adc"] = np.array(self._last_adc, dtype=np.int32)
            save_dict["sample_rate"] = np.array(self._last_rate)
        if self._last_accel is not None:
            save_dict["accel"] = self._last_accel
        # Sweep géophone par axe
        for ax_name in ("vertical", "horizontal"):
            results = self._sweep_results[ax_name]
            if not results:
                continue
            fdone = sorted(results.keys())
            for col in self._SWEEP_COLUMNS:
                if col == "note":
                    continue
                save_dict[f"{ax_name}_sweep_{col}"] = np.array(
                    [results[fr].get(col, 0) for fr in fdone],
                    dtype=np.float64 if col != "skipped" else np.bool_)
        # Transfert banc H_banc par axe (si mesuré)
        for ax_name in ("vertical", "horizontal"):
            results = self._bench_results[ax_name]
            if not results:
                continue
            fdone = sorted(results.keys())
            save_dict[f"{ax_name}_hbench_freq"] = np.array(fdone, dtype=np.float64)
            save_dict[f"{ax_name}_hbench_g_per_v"] = np.array(
                [results[fr].get("h_bench_g_per_v", 0) for fr in fdone],
                dtype=np.float64)
        # Linéarité par axe (erreur dB par fréquence)
        for ax_name in ("vertical", "horizontal"):
            entries = self._linearity_results[ax_name]
            if not entries:
                continue
            save_dict[f"{ax_name}_linearity_freq"] = np.array(
                [e["freq_hz"] for e in entries], dtype=np.float64)
            save_dict[f"{ax_name}_linearity_error_db"] = np.array(
                [e["linearity_error_db"] for e in entries], dtype=np.float64)
        # Sensibilité transversale (cross-axis)
        if self._cross_results:
            cf = sorted(self._cross_results.keys())
            save_dict["cross_axis_freq"] = np.array(cf, dtype=np.float64)
            save_dict["cross_axis_pct"] = np.array(
                [self._cross_results[f]["cross_axis_pct"] for f in cf],
                dtype=np.float64)
        np.savez(path, **save_dict)

    # ===================================================================
    # Fermeture
    # ===================================================================

    def _save_config(self):
        """Persiste les valeurs des widgets dans config.ini."""
        # Synchronise les champs APS de l'axe actif vers les dicts
        axis = self._vars["aps_axis"].get()
        self._aps_ctrl_ports[axis] = self._vars["aps_ctrl_port"].get()
        self._aps125_gains[axis]   = self._vars["aps125_gain"].get()
        self._aps125_climits[axis] = self._vars["aps125_climit"].get()

        sv = _cfg_mgr.set_value
        sv("ADS1285", "bridge_port",  self._vars["ads_port"].get())
        sv("ADS1285", "sample_rate",  self._vars["ads_rate"].get())
        sv("ADS1285", "num_samples",  self._vars["ads_count"].get())
        sv("Wavetek",  "port",         self._vars["wav_port"].get())
        sv("APS", "controller_vertical_port",   self._aps_ctrl_ports["vertical"])
        sv("APS", "controller_horizontal_port", self._aps_ctrl_ports["horizontal"])
        sv("APS", "amplifier_gain_vertical",    self._aps125_gains["vertical"])
        sv("APS", "amplifier_gain_horizontal",  self._aps125_gains["horizontal"])
        sv("APS", "amplifier_current_limit_vertical",   self._aps125_climits["vertical"])
        sv("APS", "amplifier_current_limit_horizontal", self._aps125_climits["horizontal"])
        sv("NI",  "device_name",         self._vars["accel_dev"].get())
        sv("NI",  "ai_channels",         self._vars["accel_ch"].get())
        sv("NI",  "sample_rate",         self._vars["accel_rate"].get())
        sv("NI",  "samples_per_channel", self._vars["accel_spc"].get())
        sv("Shaker", "envelope_fraction", self._vars["cal_fraction"].get())
        sv("Shaker", "accel_cap_g",       self._vars["cal_cap"].get())
        sv("Shaker", "geophone",          self._vars["cal_geophone"].get())
        _cfg_mgr.save()

    def _on_close(self):
        self._stop_event.set()
        self._set_status("Fermeture...")
        self.update_idletasks()
        self._save_config()
        self._dm.disconnect_all()
        self.destroy()


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = Application()
    app.mainloop()
