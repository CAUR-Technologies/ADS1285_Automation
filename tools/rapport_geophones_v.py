"""
Génère les figures et la synthèse du rapport de calibration des géophones
VERTICAUX (run du 2026-06-05).

Sortie : data/rapport_geophones_V_2026-06-05/figures/*.png  + résumé console.

Source des données :
- transfert de banc : data/H_Banc/transfert_banc_vertical_<ts>.csv
- balayages géophone : data/<dut>/balayage_<dut>_vertical_<ts>.csv (+ onde_*.npz par point)

Adapté de tools/rapport_geophones.py (axe horizontal). Lancer :
    python tools/rapport_geophones_v.py
"""

import os
import sys
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
from equipment import geophones as geo_specs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "rapport_geophones_V_2026-06-05", "figures")
os.makedirs(OUT, exist_ok=True)

AXIS = "vertical"
# ADS1285 : 32 bits signés, ±2,5 V crête à gain 1
COUNTS_PER_VOLT = (2 ** 31) / 2.5
SNR_OK_DB = 20.0  # seuil de fiabilité du logiciel

BENCH_CSV = os.path.join(DATA, "H_Banc",
                         "transfert_banc_vertical_2026-06-05_15-13-39.csv")

# (label, spec_key, sous-dossier, fichier balayage, timestamp onde, couleur)
DUTS = [
    ("HG-6XT UB",   "HG-6XT UB",   "HG-6XT-UB",
     "balayage_HG-6XT-UB_vertical_2026-06-05_16-43-28.csv", "2026-06-05_16-43-28", "#1f77b4"),
    ("VAS-200 (V)", "VAS-200 (V)", "VAS-200-V",
     "balayage_VAS-200-V_vertical_2026-06-05_16-25-22.csv", "2026-06-05_16-25-22", "#d62728"),
]


def parse_sweep(path):
    """Retourne (meta dict, rows list[dict], fit dict)."""
    meta, fit, cols, rows = {}, {}, None, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                body = line[1:].strip()
                if ":" in body:
                    k, v = body.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k.startswith("fit_"):
                        fk = {"fit_f0_hz": "f0", "fit_G0_counts_per_mps": "G0",
                              "fit_zeta": "zeta",
                              "fit_rms_error_db": "rms_error_db"}.get(k, k[4:])
                        try:
                            fit[fk] = float(v)
                        except ValueError:
                            pass
                    else:
                        meta[k] = v
                continue
            if cols is None:
                cols = line.split(",")
                continue
            parts = line.split(",")
            if len(parts) < len(cols):
                continue  # ligne d'erreur multi-lignes : ignorée
            row = dict(zip(cols, parts))
            rows.append(row)
    return meta, rows, fit


def fcol(rows, key):
    out = []
    for r in rows:
        try:
            out.append(float(r[key]))
        except (ValueError, KeyError):
            out.append(np.nan)
    return np.array(out)


def load_sweep(label, subdir, fname):
    path = os.path.join(DATA, subdir, fname)
    meta, rows, fit = parse_sweep(path)
    rows = [r for r in rows if r.get("skipped", "False") != "True"]
    d = {
        "label": label, "path": path, "meta": meta, "fit": fit,
        "freq": fcol(rows, "freq_hz"),
        "sens_g": fcol(rows, "sensitivity_counts_per_g"),
        "sens_v": fcol(rows, "sensitivity_counts_per_mps"),
        "snr": fcol(rows, "snr_db"),
        "thd": fcol(rows, "thd_percent"),
        "vel": fcol(rows, "peak_velocity_mps"),
        "meas_g": fcol(rows, "measured_g"),
    }
    d["reliable"] = d["snr"] >= SNR_OK_DB
    return d


def load_onde(subdir, label_slug, freq, ts):
    fn = f"onde_{label_slug}_{AXIS}_{freq:g}Hz_{ts}.npz"
    path = os.path.join(DATA, subdir, fn)
    if not os.path.exists(path):
        return None
    return np.load(path, allow_pickle=True)


# ---------------------------------------------------------------- chargement
bmeta, brows, _ = parse_sweep(BENCH_CSV)
bench = {
    "freq": fcol(brows, "freq_hz"),
    "h": fcol(brows, "h_bench_g_per_v"),
    "snr": fcol(brows, "snr_db"),
    "thd": fcol(brows, "thd_percent"),
}
bench["reliable"] = bench["snr"] >= SNR_OK_DB

sweeps = [load_sweep(lbl, sub, fn) for (lbl, _k, sub, fn, _ts, _c) in DUTS]
colors = {lbl: c for (lbl, _k, _s, _f, _ts, c) in DUTS}
slugs = {lbl: (sub, sub, ts) for (lbl, _k, sub, _f, ts, _c) in DUTS}

# =============================================================== FIGURE 1 : banc
fig, ax = plt.subplots(figsize=(7.5, 4.5))
ax.loglog(bench["freq"], bench["h"], "o-", color="#555", lw=1.4, ms=5,
          label="H_banc(f) mesuré")
rel = bench["reliable"]
ax.loglog(bench["freq"][~rel], bench["h"][~rel], "o", mfc="white",
          mec="#c00", ms=9, label=f"SNR < {SNR_OK_DB:.0f} dB (rejeté)")
ax.set_xlabel("Fréquence (Hz)")
ax.set_ylabel("H_banc  (g / V)")
ax.set_title("Fonction de transfert du banc — axe vertical\n"
             "accéléromètre de référence / commande Wavetek")
ax.grid(True, which="both", alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig1_transfert_banc.png"), dpi=130)
plt.close(fig)

# ============================================ FIGURE 2 : sensibilité vitesse + fit
fig, ax = plt.subplots(figsize=(8, 5))
ffit = np.logspace(np.log10(0.1), np.log10(100), 300)
for s in sweeps:
    c = colors[s["label"]]
    rel = s["reliable"]
    ax.loglog(s["freq"][rel], s["sens_v"][rel], "o", color=c, ms=6,
              label=f"{s['label']}")
    ax.loglog(s["freq"][~rel], s["sens_v"][~rel], "o", mfc="white", mec=c, ms=6)
    fit = s["fit"]
    if {"G0", "f0", "zeta"} <= fit.keys():
        model = dsp.geophone_velocity_response(ffit, fit["G0"], fit["f0"], fit["zeta"])
        ax.loglog(ffit, model, "--", color=c, lw=1.2, alpha=0.8)
ax.set_xlabel("Fréquence (Hz)")
ax.set_ylabel("Sensibilité  (counts / (m/s))")
ax.set_title("Fonction de transfert des géophones verticaux (réponse en vitesse)\n"
             "points pleins = SNR ≥ 20 dB, creux = bruit ; tirets = modèle 2ᵉ ordre")
ax.grid(True, which="both", alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig2_sensibilite_velocite.png"), dpi=130)
plt.close(fig)

# ============================================ FIGURE 3 : réponses normalisées
fig, ax = plt.subplots(figsize=(8, 5))
for s in sweeps:
    c = colors[s["label"]]
    rel = s["reliable"]
    f = s["freq"][rel]
    sv = s["sens_v"][rel]
    plateau = np.median(sv[f >= 10]) if np.any(f >= 10) else np.nanmax(sv)
    ax.semilogx(f, 20 * np.log10(sv / plateau), "o-", color=c, ms=6,
                label=f"{s['label']}  (plateau ≈ {plateau:.2e})")
ax.axhline(0, color="k", lw=0.7, ls=":")
ax.axhline(-3, color="grey", lw=0.7, ls=":")
ax.text(0.11, -2.6, "-3 dB", fontsize=8, color="grey")
ax.set_xlabel("Fréquence (Hz)")
ax.set_ylabel("Réponse normalisée (dB, réf. plateau)")
ax.set_title("Réponses normalisées — comparaison des fréquences de coupure")
ax.grid(True, which="both", alpha=0.3)
ax.legend()
ax.set_ylim(-45, 6)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig3_normalisee.png"), dpi=130)
plt.close(fig)

# ============================================ FIGURE 4 : FFT normalisée @ 5 Hz
F_FFT = 5.0
fig, axes = plt.subplots(1, len(sweeps), figsize=(9, 4.2), sharey=True)
if len(sweeps) == 1:
    axes = [axes]
for ax, s in zip(axes, sweeps):
    lbl = s["label"]
    sub, slug, ts = slugs[lbl]
    npz = load_onde(sub, slug, F_FFT, ts)
    c = colors[lbl]
    if npz is None:
        ax.set_title(f"{lbl}\n(onde {F_FFT:g} Hz absente)")
        continue
    x = npz["geo_wave"].astype(np.float64)
    fs = float(npz["geo_rate"])
    x = x - np.mean(x)
    win = np.hanning(len(x))
    X = np.abs(np.fft.rfft(x * win))
    freqs = np.fft.rfftfreq(len(x), 1.0 / fs)
    X_db = 20 * np.log10(X / X.max() + 1e-12)
    ax.plot(freqs, X_db, color=c, lw=1.0)
    thd = float(npz["thd_percent"]) if "thd_percent" in npz else np.nan
    for k in range(2, 7):
        ax.axvline(k * F_FFT, color="grey", ls=":", lw=0.6)
    ax.axvline(F_FFT, color="k", ls="--", lw=0.8)
    ax.set_xlim(0, 6 * F_FFT)
    ax.set_ylim(-90, 3)
    ax.set_title(f"{lbl}  @ {F_FFT:g} Hz\nTHD = {thd:.2f} %")
    ax.set_xlabel("Fréquence (Hz)")
    ax.grid(True, alpha=0.3)
axes[0].set_ylabel("Magnitude normalisée (dB)")
fig.suptitle("FFT normalisée du signal géophone (fondamentale = 0 dB ; "
             "pointillés = harmoniques 2f…6f)", y=1.02)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig4_fft_normalisee.png"), dpi=130, bbox_inches="tight")
plt.close(fig)

# ============================================ FIGURE 5 : THD vs fréquence
fig, ax = plt.subplots(figsize=(7.5, 4.5))
for s in sweeps:
    c = colors[s["label"]]
    rel = s["reliable"]
    ax.semilogx(s["freq"][rel], s["thd"][rel], "o-", color=c, ms=6, label=s["label"])
ax.set_xlabel("Fréquence (Hz)")
ax.set_ylabel("THD (%)")
ax.set_title("Distorsion harmonique totale du signal géophone\n(points fiables, SNR ≥ 20 dB)")
ax.grid(True, which="both", alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig5_thd.png"), dpi=130)
plt.close(fig)

# ============================ FIGURE 6 : ondes temporelles (HG-6XT UB @ 5 Hz)
ref_lbl = "HG-6XT UB"
sub, slug, ts = slugs[ref_lbl]
npz = load_onde(sub, slug, 5.0, ts)
if npz is not None:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    acc = npz["accel_wave"].astype(float)
    fa = float(npz["accel_fs"])
    ta = np.arange(len(acc)) / fa
    a1.plot(ta, acc, color="#555", lw=0.9)
    a1.set_ylabel("Accél. réf. (g)")
    a1.grid(True, alpha=0.3)
    a1.set_title(f"Signaux bruts simultanés — {ref_lbl} @ 5 Hz")
    g = npz["geo_wave"].astype(float)
    g = g - np.mean(g)
    fg = float(npz["geo_rate"])
    tg = np.arange(len(g)) / fg
    a2.plot(tg, g / 1e6, color="#1f77b4", lw=0.9)
    a2.set_ylabel("Géophone (Mcounts, DC retiré)")
    a2.set_xlabel("Temps (s)")
    a2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig6_ondes.png"), dpi=130)
    plt.close(fig)

# ===================================================================== RÉSUMÉ
print("\n================  SYNTHÈSE — GÉOPHONES VERTICAUX  ================\n")
print(f"{'Geophone':12} | {'plateau cnt/(m/s)':18} | {'V/(m/s) mes.':12} | "
      f"{'V/(m/s) spec':12} | {'fit f0':7} | {'fit zeta':8} | {'rms dB':6}")
print("-" * 92)
for s in sweeps:
    lbl = s["label"]
    rel = s["reliable"]
    f, sv = s["freq"][rel], s["sens_v"][rel]
    plateau = np.median(sv[f >= 10]) if np.any(f >= 10) else np.nan
    v_meas = plateau / COUNTS_PER_VOLT
    spec = geo_specs.GEOPHONE_SPECS.get(lbl)
    v_spec = spec[0] if spec else np.nan
    fit = s["fit"]
    print(f"{lbl:12} | {plateau:18.3e} | {v_meas:12.1f} | {v_spec:12.1f} | "
          f"{fit.get('f0', float('nan')):7.2f} | {fit.get('zeta', float('nan')):8.2f} | "
          f"{fit.get('rms_error_db', float('nan')):6.2f}")

print("\nBande fiable (SNR >= 20 dB) par géophone :")
for s in sweeps:
    f = s["freq"][s["reliable"]]
    if len(f):
        print(f"  {s['label']:12} : {f.min():g} – {f.max():g} Hz  ({len(f)} points)")
    else:
        print(f"  {s['label']:12} : aucun point fiable")

print("\nTransfert de banc (g/V), points fiables :")
for fr, h, r in zip(bench["freq"], bench["h"], bench["reliable"]):
    print(f"  {fr:5g} Hz : {h:.4f}  {'' if r else '(rejeté SNR)'}")

print(f"\nFigures écrites dans {OUT}")
