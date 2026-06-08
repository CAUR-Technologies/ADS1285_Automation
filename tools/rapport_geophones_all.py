"""
Rapport COMBINÉ de calibration — 8 géophones (5 verticaux + 3 horizontaux)
caractérisés du 2026-06-05 au 2026-06-08.

Génère figures + synthèse console (planchers de bruit inclus).
Sortie : data/rapport_geophones_ALL_2026-06-08/figures/*.png

Lancer :  python tools/rapport_geophones_all.py
"""
import os, sys, glob
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment import dsp  # noqa: E402
from equipment import geophones as gs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "rapport_geophones_ALL_2026-06-08", "figures")
os.makedirs(OUT, exist_ok=True)
CPV = (2 ** 31) / 2.5
SNR_OK = 20.0

BENCH = {
    "vertical":   os.path.join(DATA, "H_Banc", "transfert_banc_vertical_2026-06-05_15-13-39.csv"),
    "horizontal": os.path.join(DATA, "H_Banc", "transfert_banc_horizontal_2026-06-08_11-30-24.csv"),
}

# (label, axis, sous-dossier/fichier, timestamp onde, couleur)
DUTS = [
    ("HG-6XT UB",   "vertical",   "HG-6XT-UB/balayage_HG-6XT-UB_vertical_2026-06-05_16-43-28.csv",  "2026-06-05_16-43-28", "#1f77b4"),
    ("VAS-200 (V)", "vertical",   "VAS-200-V/balayage_VAS-200-V_vertical_2026-06-05_16-25-22.csv",  "2026-06-05_16-25-22", "#d62728"),
    ("HG-5VHS",     "vertical",   "HG-5VHS/balayage_HG-5VHS_vertical_2026-06-08_10-09-02.csv",      "2026-06-08_10-09-02", "#ff7f0e"),
    ("HG-2 U",      "vertical",   "HG-2-U/balayage_HG-2-U_vertical_2026-06-08_10-31-38.csv",        "2026-06-08_10-31-38", "#9467bd"),
    ("ST-2A (V)",   "vertical",   "ST-2A-V/balayage_ST-2A-V_vertical_2026-06-08_11-09-54.csv",      "2026-06-08_11-09-54", "#2ca02c"),
    ("HG-6 HB",     "horizontal", "HG-6-HB/balayage_HG-6-HB_horizontal_2026-06-08_11-51-30.csv",    "2026-06-08_11-51-30", "#1f77b4"),
    ("VAS-H-200",   "horizontal", "VAS-H-200/balayage_VAS-H-200_horizontal_2026-06-08_13-24-35.csv","2026-06-08_13-24-35", "#d62728"),
    ("ST-2A (H)",   "horizontal", "ST-2A-H/balayage_ST-2A-H_horizontal_2026-06-08_13-37-30.csv",    "2026-06-08_13-37-30", "#2ca02c"),
]


def parse(path):
    fit, cols, rows = {}, None, []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("#"):
            b = line[1:].strip()
            if ":" in b:
                k, v = b.split(":", 1); k = k.strip()
                if k.startswith("fit_"):
                    try: fit[k] = float(v.strip())
                    except ValueError: pass
            continue
        if cols is None: cols = line.split(","); continue
        p = line.split(",")
        if len(p) >= len(cols): rows.append(dict(zip(cols, p)))
    return rows, fit


def col(rows, k):
    o = []
    for r in rows:
        try: o.append(float(r[k]))
        except (ValueError, KeyError): o.append(np.nan)
    return np.array(o)


def load_dut(lbl, axis, fn):
    rows, fit = parse(os.path.join(DATA, fn))
    rows = [r for r in rows if r.get("skipped", "False") != "True"]
    d = {"label": lbl, "axis": axis, "fit": fit,
         "freq": col(rows, "freq_hz"), "sens_v": col(rows, "sensitivity_counts_per_mps"),
         "snr": col(rows, "snr_db"), "thd": col(rows, "thd_percent")}
    d["rel"] = d["snr"] >= SNR_OK
    f, sv = d["freq"][d["rel"]], d["sens_v"][d["rel"]]
    d["plateau"] = np.nanmedian(sv[f >= 10]) if np.any(f >= 10) else np.nan
    return d


def load_bench(path):
    rows, _ = parse(path)
    return {"freq": col(rows, "freq_hz"), "h": col(rows, "h_bench_g_per_v"),
            "snr": col(rows, "snr_db"), "rel": col(rows, "snr_db") >= SNR_OK}


def load_onde(fn_csv, ts, freq):
    sub = fn_csv.split("/")[0]
    axis = "vertical" if "vertical" in fn_csv else "horizontal"
    p = os.path.join(DATA, sub, f"onde_{sub}_{axis}_{freq:g}Hz_{ts}.npz")
    return np.load(p, allow_pickle=True) if os.path.exists(p) else None


def noise_floor(axis):
    fs = sorted(glob.glob(os.path.join(DATA, f"plancher_bruit_{axis}_*.npz")))
    if not fs: return np.nan
    return float(np.load(fs[-1], allow_pickle=True)["plancher_g_rms"]) * 1000  # mg


duts = [load_dut(l, a, f) for (l, a, f, _ts, _c) in DUTS]
colors = {l: c for (l, _a, _f, _ts, c) in DUTS}
ts_of = {l: ts for (l, _a, f, ts, _c) in DUTS}
fn_of = {l: f for (l, _a, f, ts, _c) in DUTS}
nf = {"vertical": noise_floor("vertical"), "horizontal": noise_floor("horizontal")}
benches = {a: load_bench(p) for a, p in BENCH.items()}

# ===== FIG 1 : H_banc V + H
fig, ax = plt.subplots(figsize=(8, 4.6))
for a, c, m in (("vertical", "#1f77b4", "o"), ("horizontal", "#d62728", "s")):
    b = benches[a]
    ax.loglog(b["freq"], b["h"], m + "-", color=c, ms=5, lw=1.3, label=f"H_banc {a}")
    ax.loglog(b["freq"][~b["rel"]], b["h"][~b["rel"]], m, mfc="white", mec=c, ms=9)
ax.set_xlabel("Fréquence (Hz)"); ax.set_ylabel("H_banc (g/V)")
ax.set_title("Fonctions de transfert des bancs — vertical & horizontal\n(symboles creux = SNR < 20 dB)")
ax.grid(True, which="both", alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_hbanc_VH.png"), dpi=130); plt.close(fig)

# ===== FIG 2 : sensibilité vitesse (un panneau par axe)
ffit = np.logspace(np.log10(0.1), np.log10(100), 300)
for axis, fname in (("vertical", "fig2v_sensibilite_V.png"), ("horizontal", "fig2h_sensibilite_H.png")):
    fig, ax = plt.subplots(figsize=(8, 5))
    for d in [x for x in duts if x["axis"] == axis]:
        c = colors[d["label"]]
        ax.loglog(d["freq"][d["rel"]], d["sens_v"][d["rel"]], "o", color=c, ms=6, label=d["label"])
        ax.loglog(d["freq"][~d["rel"]], d["sens_v"][~d["rel"]], "o", mfc="white", mec=c, ms=6)
        fit = d["fit"]
        if {"fit_G0_counts_per_mps", "fit_f0_hz", "fit_zeta"} <= fit.keys():
            model = dsp.geophone_velocity_response(ffit, fit["fit_G0_counts_per_mps"], fit["fit_f0_hz"], fit["fit_zeta"])
            ax.loglog(ffit, model, "--", color=c, lw=1.1, alpha=0.8)
    ax.set_xlabel("Fréquence (Hz)"); ax.set_ylabel("Sensibilité (counts/(m/s))")
    ax.set_title(f"Sensibilité en vitesse — géophones {axis}\npoints pleins SNR≥20 dB, creux=bruit, tirets=modèle 2ᵉ ordre")
    ax.grid(True, which="both", alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=130); plt.close(fig)

# ===== FIG 3 : normalisées (8, lignes pleines=V, tirets=H)
fig, ax = plt.subplots(figsize=(9, 5.2))
for d in duts:
    c = colors[d["label"]]; ls = "-" if d["axis"] == "vertical" else "--"
    f, sv = d["freq"][d["rel"]], d["sens_v"][d["rel"]]
    if not len(f): continue
    ax.semilogx(f, 20 * np.log10(sv / d["plateau"]), ls, marker="o", color=c, ms=5,
                label=f"{d['label']} ({d['axis'][0].upper()})")
ax.axhline(0, color="k", lw=0.7, ls=":"); ax.axhline(-3, color="grey", lw=0.7, ls=":")
ax.set_xlabel("Fréquence (Hz)"); ax.set_ylabel("Réponse normalisée (dB, réf. plateau)")
ax.set_title("Réponses normalisées des 8 géophones (pleins=V, tirets=H)")
ax.grid(True, which="both", alpha=0.3); ax.legend(ncol=2, fontsize=8); ax.set_ylim(-45, 6)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_normalisee.png"), dpi=130); plt.close(fig)

# ===== FIG 4 : THD
fig, ax = plt.subplots(figsize=(8, 4.6))
for d in duts:
    c = colors[d["label"]]; ls = "-" if d["axis"] == "vertical" else "--"
    ax.semilogx(d["freq"][d["rel"]], d["thd"][d["rel"]], ls, marker="o", color=c, ms=5,
                label=f"{d['label']} ({d['axis'][0].upper()})")
ax.set_xlabel("Fréquence (Hz)"); ax.set_ylabel("THD (%)")
ax.set_title("Distorsion harmonique totale (points fiables)")
ax.grid(True, which="both", alpha=0.3); ax.legend(ncol=2, fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_thd.png"), dpi=130); plt.close(fig)

# ===== FIG 5 : illustration limite BF (H_banc vs plancher de bruit, axe V)
fig, ax = plt.subplots(figsize=(8, 4.6))
b = benches["vertical"]
acc_mg = b["h"] * 0  # placeholder
# l'accélération réellement appliquée est dans le CSV H_banc ? on prend target via h*vpp non dispo ici
# -> on illustre le plancher de bruit comme ligne horizontale
ax.axhline(nf["vertical"], color="#d62728", lw=1.5, ls="--", label=f"plancher bruit V = {nf['vertical']:.2f} mg RMS")
ax.axhline(nf["horizontal"], color="#1f77b4", lw=1.5, ls=":", label=f"plancher bruit H = {nf['horizontal']:.2f} mg RMS")
# enveloppe d'accélération max (displacement-limited) à envelope_fraction=0.6, stroke 38 mm
fr = np.logspace(np.log10(0.1), np.log10(100), 200)
a_env = 0.6 * (0.038) * (2 * np.pi * fr) ** 2 / 9.80665 * 1000  # mg
a_cap = np.minimum(a_env, 200)  # plafond accel 0.2 g
ax.loglog(fr, a_cap, "k-", lw=1.5, label="accél. max appliquée (enveloppe 0,6·stroke, plafond 0,2 g)")
ax.set_xlabel("Fréquence (Hz)"); ax.set_ylabel("Accélération (mg)")
ax.set_title("Pourquoi la basse fréquence est limitée :\nl'accélération réalisable (displacement-limited) rejoint le plancher de bruit")
ax.grid(True, which="both", alpha=0.3); ax.legend(fontsize=8); ax.set_ylim(0.1, 500)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig5_limite_bf.png"), dpi=130); plt.close(fig)

# ===================== SYNTHÈSE =====================
print("\n========  SYNTHÈSE — 8 GÉOPHONES (V+H), 2026-06-05 → 2026-06-08  ========\n")
print(f"{'Géophone':12} {'ax':3} {'V/(m/s) mes':11} {'spec':7} {'écart':7} {'f0':5} {'ζ':5} {'rms':5} {'bande fiable':13}")
print("-" * 88)
for d in duts:
    sp = gs.GEOPHONE_SPECS.get(d["label"]); vsp = sp[0] if sp else np.nan
    vms = d["plateau"] / CPV
    ecart = (vms / vsp - 1) * 100 if vsp else np.nan
    fb = d["freq"][d["rel"]]
    band = f"{fb.min():g}-{fb.max():g}Hz" if len(fb) else "—"
    fit = d["fit"]
    print(f"{d['label']:12} {d['axis'][0].upper():3} {vms:11.1f} {vsp:7.1f} {ecart:+6.0f}% "
          f"{fit.get('fit_f0_hz', float('nan')):5.2f} {fit.get('fit_zeta', float('nan')):5.2f} "
          f"{fit.get('fit_rms_error_db', float('nan')):5.2f} {band:13}")
print(f"\nPlancher de bruit (accél. réf.) : V = {nf['vertical']:.2f} mg RMS, H = {nf['horizontal']:.2f} mg RMS")
print(f"Figures : {OUT}")
