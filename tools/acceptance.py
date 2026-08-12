#!/usr/bin/env python
"""
Banc d'ACCEPTATION PRODUIT (go/no-go design) — 9 prototypes, USB seul, PAS de shaker.

Exécute par unité (~5 min) les tests atteignables via l'interface CDC, mappés sur la
matrice de validation matérielle V1–V15 (geophones-firmware/doc/hardware). Écrit un
verdict PASS/WARN/FAIL par test dans `data/acceptance/<serial>.json`, et un tableau
de bord FLOTTE (`--fleet`).

Le test clé = **V7 (µSD + stress transfert)** : enregistre puis récupère TOUT le
survey en mesurant corruption ET **freeze** — sur 1 unité c'est un incident, sur 9
ça dit si le gel-sous-charge est un défaut de DESIGN.

Usage :
    python tools/acceptance.py                 # auto-découvre l'unité branchée
    python tools/acceptance.py --rec 120       # durée d'enregistrement du stress (s)
    python tools/acceptance.py --fleet         # tableau de bord des 9 unités
"""
import datetime
import json
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from equipment.geophone3axis.geophone3axis import discover_units, Geophone3Axis
from equipment.geophone3axis import dat_reader
from config.settings import GEOPHONE3AXIS_VID, GEOPHONE3AXIS_PID

OUT_DIR = "data/acceptance"
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _call_timeout(fn, timeout_s):
    """Exécute fn() dans un thread ; retourne (résultat, timed_out). Sert à détecter
    un FREEZE du board sans bloquer 120 s sur le timeout série interne."""
    box = {}
    def _run():
        try:
            box["r"] = fn()
        except Exception as e:   # noqa: BLE001
            box["e"] = e
    th = threading.Thread(target=_run, daemon=True)
    th.start(); th.join(timeout_s)
    if th.is_alive():
        return None, True
    if "e" in box:
        raise box["e"]
    return box.get("r"), False


class Frozen(Exception):
    """Le board ne répond plus (freeze) — un appel a dépassé son timeout."""


class SafeUnit:
    """Proxy anti-freeze : chaque commande board tourne sous timeout ; un dépassement
    lève `Frozen(label)` au lieu de bloquer le harnais 120 s. INDISPENSABLE pour la
    flotte : une unité qui gèle est NOTÉE (FREEZE=FAIL) sans figer la campagne."""
    _T = {"status": 8, "config": 8, "set_config": 10, "start": 8, "stop": 8,
          "sync": 8, "ls": 12, "get_file": 20}

    def __init__(self, g):
        self.g = g

    def _s(self, name, *a, **k):
        r, to = _call_timeout(lambda: getattr(self.g, name)(*a, **k), self._T[name])
        if to:
            raise Frozen(name)
        return r

    def status(self): return self._s("status")
    def config(self): return self._s("config")
    def set_config(self, f): return self._s("set_config", f)
    def start(self): return self._s("start")
    def stop(self): return self._s("stop")
    def sync(self): return self._s("sync")
    def ls(self, p=""): return self._s("ls", p)
    def get_file(self, p): return self._s("get_file", p)

    @property
    def serial_number(self): return self.g.serial_number
    @property
    def _lock(self): return self.g._lock
    def _open(self): return self.g._open()


# ── tests unitaires (chacun retourne dict {test, verdict, detail}) ──────────

def v1_boot(g):
    """V1 — boot & console : STATUS répété, uptime monotone, pas de reboot."""
    ups, sn = [], None
    for _ in range(3):
        st = g.status(); ups.append(st.get("uptime_s")); sn = st.get("serial")
        time.sleep(4)
    ok = all(isinstance(u, (int, float)) for u in ups) and ups[0] < ups[-1]
    return {"test": "V1 boot", "verdict": PASS if ok else FAIL,
            "detail": f"uptime {ups} s, serial={sn}"}


def v13_identity(g, expect_serial):
    """V13 — identité + révision HW (MAX7319)."""
    st = g.status()
    sn, hw = st.get("serial"), st.get("hwrev")
    ok = sn == expect_serial and hw is not None and st.get("fw")
    return {"test": "V13 identité/rev", "verdict": PASS if ok else FAIL,
            "detail": f"serial={sn} fw={st.get('fw')} git={st.get('git')} hwrev={hw}"}


def v6_imu(g):
    """V6 — IMU : STREAM ON, vecteur g cohérent (~1 g) et tilt fini."""
    import serial  # noqa: F401
    gmags, tilts, n = [], [], 0
    with g._lock:
        ser = g._open(); ser.reset_input_buffer()
        ser.write(b"STREAM ON\n"); ser.flush(); time.sleep(0.4)
        t0 = time.time()
        while time.time() - t0 < 2.5:
            ln = ser.readline().decode(errors="replace").strip()
            if ln.startswith("IMU") and "ERR" not in ln:
                p = ln.split(",")
                if len(p) >= 10:
                    ax, ay, az = int(p[1]), int(p[2]), int(p[3])   # milli-g
                    gmags.append((ax**2 + ay**2 + az**2) ** 0.5 / 1000.0)
                    tilts.append(int(p[9]) / 100.0); n += 1
        ser.write(b"STREAM OFF\n"); ser.flush()
    if not gmags:
        return {"test": "V6 IMU", "verdict": FAIL, "detail": "aucune trame IMU"}
    gm = float(np.median(gmags))
    ok = 0.8 <= gm <= 1.2 and n >= 3
    return {"test": "V6 IMU", "verdict": PASS if ok else WARN,
            "detail": f"|g|={gm:.3f} (n={n}), incl≈{np.median(tilts):.1f}°"}


def cfg_roundtrip(g):
    """CFG — CONFIG SET/GET aller-retour (sur survey_id, restauré ensuite)."""
    cfg0 = g.config(); orig = cfg0.get("survey_id", "default")
    probe = "ACCTEST"
    g.set_config({"survey_id": probe})
    got = g.config().get("survey_id")
    g.set_config({"survey_id": orig})   # restaure
    ok = got == probe
    return {"test": "CFG roundtrip", "verdict": PASS if ok else FAIL,
            "detail": f"écrit {probe} → relu {got}"}


def v11_battery(g):
    """V11 — tension batterie plausible."""
    b = g.status().get("battery")
    if not isinstance(b, (int, float)):
        return {"test": "V11 batterie", "verdict": FAIL, "detail": f"battery={b}"}
    if b <= 2:
        return {"test": "V11 batterie", "verdict": WARN,
                "detail": f"battery={b} % — lecture suspecte (bug FW connu : lit 1)"}
    return {"test": "V11 batterie", "verdict": PASS if 2 < b <= 100 else WARN,
            "detail": f"battery={b} %"}


def record_and_get(g, rec_s):
    """V2 + V4 + V7 + V8 + V15 — enregistre puis récupère TOUT le survey en mesurant
    corruption et FREEZE. Retourne (liste de résultats, dossier survey)."""
    ts = datetime.datetime.now().strftime("%H%M%S")
    survey = f"ACC_{ts}"
    sp = f"/survey-data/{survey}"
    g.set_config({"sample_rate_hz": 250, "samples_by_record": 250,
                  "records_per_file": 8, "gain": 1, "survey_id": survey,
                  "max_pitch_deg": 45, "max_roll_deg": 45})
    # démarrage vérifié (STOP→START→apparition fichiers)
    try:
        g.stop(); time.sleep(0.3)
    except Exception:   # noqa: BLE001
        pass
    g.start(); g.sync()
    started, t0 = False, time.time()
    while time.time() - t0 < 12:
        time.sleep(1.5)
        try:
            if len(g.ls(sp)) > 0:
                started = True; break
        except Exception:   # noqa: BLE001
            pass
    if not started:
        try:
            g.stop()
        except Exception:   # noqa: BLE001
            pass
        r_gate = {"test": "V4/V15 acquisition", "verdict": FAIL,
                  "detail": "enregistrement NON démarré (porte GPS/tilt — fix absent ?)"}
        return [r_gate], sp
    # laisse enregistrer
    time.sleep(max(0, rec_s))
    try:
        g.stop()
    except Exception:   # noqa: BLE001
        pass
    time.sleep(0.5)

    # ---- V7 stress transfert : GET tout le survey, timeout court par fichier ----
    try:
        files = sorted(f["path"] for f in g.ls(sp))
    except Exception as e:   # noqa: BLE001
        return [{"test": "V7 µSD/transfert", "verdict": FAIL,
                 "detail": f"LS survey échoué: {e}"}], sp
    os.makedirs(OUT_DIR, exist_ok=True)
    n_ok = n_corrupt = 0
    frozen = False
    parsed_channels = None
    gps_time_ok = False
    t_get0 = time.time()
    for i, p in enumerate(files):
        try:
            data = g.get_file(p)          # SafeUnit : timeout 20 s → Frozen
        except Frozen:
            frozen = True; break
        if not data:
            continue
        local = os.path.join(OUT_DIR, f"{g.serial_number}_{os.path.basename(p)}")
        with open(local, "wb") as fh:
            fh.write(data)
        try:
            chans = dat_reader.read_dat(local)
            n_ok += 1
            if any((c.meta.get("file", {}) or {}).get("records_skipped") for c in chans):
                n_corrupt += 1
            if parsed_channels is None and chans:
                parsed_channels = chans
                # temps GPS réel ? (année >= 2020)
                yr = datetime.datetime.utcfromtimestamp(chans[0].start_time_ns/1e9).year
                gps_time_ok = yr >= 2020
        except Exception:   # noqa: BLE001
            n_corrupt += 1
        finally:
            try: os.remove(local)
            except OSError: pass
    dt = time.time() - t_get0
    thr = (n_ok / dt) if dt > 0 else 0.0

    res = []
    # V7
    if frozen:
        res.append({"test": "V7 µSD/transfert", "verdict": FAIL,
                    "detail": f"FREEZE pendant GET après {n_ok}/{len(files)} fichiers"})
    else:
        rate = (n_corrupt / n_ok) if n_ok else 1.0
        v = PASS if rate == 0 else (WARN if rate < 0.10 else FAIL)
        res.append({"test": "V7 µSD/transfert", "verdict": v,
                    "detail": f"{n_ok}/{len(files)} lus, {n_corrupt} corrompus "
                              f"({rate*100:.0f}%), {thr:.1f} fich/s"})
    # V2 — 3 voies vivantes, non plates, non saturées
    if parsed_channels:
        ids = sorted(c.channel_id for c in parsed_channels)
        stds = {c.channel_id: float(np.std(c.data)) for c in parsed_channels}
        railed = any(np.max(np.abs(c.data)) >= 0.98 * 2**31 for c in parsed_channels)
        alive = all(s > 5 for s in stds.values())  # >5 counts RMS = pas figé à 0
        v2ok = len(parsed_channels) >= 3 and alive and not railed
        res.append({"test": "V2 ADC ×3", "verdict": PASS if v2ok else FAIL,
                    "detail": f"voies={ids} std={ {k: round(v) for k,v in stds.items()} } "
                              f"{'SATURÉ' if railed else ''}"})
    else:
        res.append({"test": "V2 ADC ×3", "verdict": FAIL, "detail": "aucun .dat lisible"})
    # V8 miniSEED
    res.append({"test": "V8 miniSEED", "verdict": PASS if n_ok and not frozen else FAIL,
                "detail": f"{n_ok} fichiers parsés (simplemseed v3)"})
    # V4/V15 — recording a démarré (porte GPS OK) + timestamps GPS réels + 3 voies
    v15ok = started and parsed_channels and len(parsed_channels) >= 3 and gps_time_ok and not frozen
    res.append({"test": "V4/V15 acquisition E2E", "verdict": PASS if v15ok else WARN,
                "detail": f"gate OK, {'timestamps GPS réels' if gps_time_ok else 'horodatage non-GPS ?'}"})
    return res, sp


def run_unit(rec_s=90):
    found, to = _call_timeout(
        lambda: discover_units(vid=GEOPHONE3AXIS_VID, pid=GEOPHONE3AXIS_PID), 15)
    if to:
        print("Board injoignable (découverte gelée) — RESET l'unité puis relance.")
        return None
    if not found:
        print("Aucune unité détectée (USB ?)."); return None
    sn, port = found[0]
    print(f"=== ACCEPTATION {sn} @ {port} (stress {rec_s} s) ===")
    raw = Geophone3Axis(port, serial_number=sn)
    _, to = _call_timeout(raw.connect, 10)
    if to:
        print(f"{sn} : connexion gelée — RESET requis."); return None
    g = SafeUnit(raw)          # tout appel board sous timeout anti-freeze
    results = []
    # Chaque test tourne isolé : un FREEZE le marque FAIL et on continue les suivants
    # (souvent déjà gelés → FAIL en cascade, ce qui est l'info voulue).
    def _guard(fn, label):
        try:
            results.append(fn())
        except Frozen as e:
            results.append({"test": label, "verdict": FAIL,
                            "detail": f"FREEZE (board ne répond plus sur '{e}')"})
        except Exception as e:   # noqa: BLE001
            results.append({"test": label, "verdict": FAIL, "detail": f"erreur: {e}"})
    try:
        _guard(lambda: v1_boot(g), "V1 boot")
        _guard(lambda: v13_identity(g, sn), "V13 identité/rev")
        _guard(lambda: v6_imu(g), "V6 IMU")
        _guard(lambda: cfg_roundtrip(g), "CFG roundtrip")
        _guard(lambda: v11_battery(g), "V11 batterie")
        try:
            rec_res, _ = record_and_get(g, rec_s)
            results.extend(rec_res)
        except Frozen as e:
            results.append({"test": "V7 µSD/transfert", "verdict": FAIL,
                            "detail": f"FREEZE pendant enregistrement/GET (sur '{e}')"})
    finally:
        try: raw.stop()
        except Exception: pass
        try: raw.close()
        except Exception: pass

    overall = FAIL if any(r["verdict"] == FAIL for r in results) else \
        (WARN if any(r["verdict"] == WARN for r in results) else PASS)
    rec = {"serial": sn, "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "overall": overall, "results": results, "rec_s": rec_s}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{sn}.json"), "w", encoding="utf-8") as fp:
        json.dump(rec, fp, indent=2, ensure_ascii=False)

    print(f"\n{'test':<24}{'verdict':<8}detail")
    for r in results:
        print(f"  {r['test']:<22}{r['verdict']:<8}{r['detail']}")
    print(f"\n  >>> {sn} : {overall} <<<   (data/acceptance/{sn}.json)")
    return overall


def fleet():
    import glob
    rows = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "*.json"))):
        with open(p, encoding="utf-8") as fp:
            rows.append(json.load(fp))
    if not rows:
        print("Aucun résultat. Lance d'abord `python tools/acceptance.py` sur chaque unité.")
        return
    tests = []
    for r in rows:
        for t in r["results"]:
            key = t["test"].split()[0]
            if key not in tests:
                tests.append(key)
    print(f"\n=== TABLEAU DE BORD FLOTTE ({len(rows)} unités) ===")
    print(f"{'serial':<14}{'OVERALL':<9}" + "".join(f"{t:<7}" for t in tests))
    for r in sorted(rows, key=lambda x: x["serial"]):
        by = {t["test"].split()[0]: t["verdict"] for t in r["results"]}
        line = f"{r['serial']:<14}{r['overall']:<9}"
        for t in tests:
            v = by.get(t, "-")
            line += f"{('.' if v==PASS else '!' if v==WARN else 'X' if v==FAIL else '-'):<7}"
        print(line)
    print("  légende : . PASS   ! WARN   X FAIL")
    n_pass = sum(1 for r in rows if r["overall"] == PASS)
    n_fail = sum(1 for r in rows if r["overall"] == FAIL)
    print(f"\n  {n_pass} PASS · {sum(1 for r in rows if r['overall']==WARN)} WARN · {n_fail} FAIL")


if __name__ == "__main__":
    if "--fleet" in sys.argv:
        fleet()
    else:
        rec = 90
        if "--rec" in sys.argv:
            rec = int(sys.argv[sys.argv.index("--rec") + 1])
        run_unit(rec_s=rec)
