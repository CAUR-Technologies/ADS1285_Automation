"""
Orchestrateur du banc de calibration de géophones.

Coordonne la chaîne complète :
    Wavetek (AC) -> APS 0109 (offset DC + asservissement position)
                 -> APS 125 (ampli) -> Shaker APS 113 -> géophone + accéléromètre réf.

Responsabilités (la « logique de contrôle du banc » décrite dans
equipment/CLAUDE.md) :
  * plafonner l'amplitude pour rester dans la course mécanique (enveloppe stroke)
  * adapter la stiffness du contrôleur à la fréquence (découplage position/vibration)
  * asservir l'amplitude du Wavetek en boucle fermée sur l'accéléromètre réf.
  * surveiller l'overtravel et stopper immédiatement en cas de butée
  * acquérir simultanément la réponse du géophone (ADS1285) pour en déduire
    la sensibilité par fréquence

Sécurité : un overtravel peut endommager le shaker. Toute détection de butée
coupe la sortie du Wavetek et lève TestBenchAborted.
"""

import time
import threading

from equipment.aps import shaker_physics as sp
from equipment.dsp import coherent_amplitude_peak, ratio_db, linearity_error_db
from equipment.instrlog import get_logger
from constants import CAL_LINEARITY_MAX_DB, CAL_DAILY_TOL_DB, CAL_DAILY_FREQS_HZ
from config.settings import (
    SHAKER_STROKE_MM,
    SHAKER_ENVELOPE_FRACTION,
    SHAKER_ACCEL_CAP_G,
    SHAKER_ACCEL_FLOOR_G,
    SHAKER_SERVO_TOLERANCE,
    SHAKER_SERVO_MAX_ITER,
    SHAKER_SERVO_START_VPP,
)
from constants import SNR_MIN_DB


class TestBenchError(RuntimeError):
    """Erreur générale du banc."""


class TestBenchAborted(TestBenchError):
    """Séquence interrompue (overtravel, arrêt utilisateur, hors-limite)."""


class TestBench:
    """Orchestre Wavetek + APS 0109 + accéléromètre + ADS1285 (géophone)."""

    def __init__(self,
                 wavetek,
                 aps,
                 accelerometer,
                 ads1285=None,
                 *,
                 stroke_mm: float = SHAKER_STROKE_MM,
                 envelope_fraction: float = SHAKER_ENVELOPE_FRACTION,
                 accel_cap_g: float = SHAKER_ACCEL_CAP_G,
                 accel_floor_g: float = SHAKER_ACCEL_FLOOR_G,
                 servo_tolerance: float = SHAKER_SERVO_TOLERANCE,
                 servo_max_iter: int = SHAKER_SERVO_MAX_ITER,
                 servo_start_vpp: float = SHAKER_SERVO_START_VPP,
                 vpp_max: float = 5.0,
                 ref_channel: int = 0):
        self._wav = wavetek
        self._aps = aps
        self._accel = accelerometer
        self._ads = ads1285
        self._ref_channel = ref_channel   # canal accéléro de réf. pour cet axe

        self._stroke = stroke_mm
        self._fraction = envelope_fraction
        self._cap = accel_cap_g
        self._floor = accel_floor_g
        self._servo_tol = servo_tolerance
        self._servo_max_iter = servo_max_iter
        self._servo_start_vpp = servo_start_vpp
        self._vpp_max = vpp_max

        self._zer_value = 0          # dernière valeur ZER appliquée (-99..99)
        self._settle_s = 4.0         # temps de stabilisation par défaut (s)
        self._stop = None            # threading.Event optionnel
        self._aps_started = False    # le contrôleur APS a-t-il reçu STA ?
        # Journalisation : fichier unifié + callback statut (GUI)
        self._flog = get_logger("TestBench")
        self._status_cb = print
        self._log = lambda m: (self._flog.debug(m), self._status_cb(m))

        self._h_bench = {}           # {freq: H_banc en g/V} — caractérisation banc
        self._noise_floor_g = None   # plancher de bruit mesuré (g RMS)

    # ──────────────────────────────────────────────────────────────────
    # Configuration / utilitaires
    # ──────────────────────────────────────────────────────────────────

    def set_logger(self, fn):
        """Définit le callback de statut (ex. status bar du GUI). Le journal
        fichier (logs/bench.log) reste alimenté en parallèle."""
        self._status_cb = fn

    def set_stop_event(self, event):
        """Définit un threading.Event pour interrompre les séquences."""
        self._stop = event

    def _check_stop(self):
        if self._stop is not None and self._stop.is_set():
            self._safe_shutdown()
            raise TestBenchAborted("Arrêt demandé par l'utilisateur.")

    def zer_to_mm(self, zer_value: int) -> float:
        """Convertit une valeur ZER (-99..99) en offset physique approximatif (mm).

        Le manuel APS indique ZER ±99 ≈ ±10 % de la course.
        """
        return (zer_value / 99.0) * 0.10 * self._stroke

    def target_accel_g(self, freq_hz: float) -> float:
        """Accélération cible (g) pour une fréquence donnée (enveloppe plafonnée)."""
        return sp.target_accel_g(freq_hz, self._stroke,
                                 fraction=self._fraction,
                                 accel_cap_g=self._cap)

    # ──────────────────────────────────────────────────────────────────
    # Sécurité
    # ──────────────────────────────────────────────────────────────────

    def _check_overtravel(self):
        """Lit l'état d'erreur APS ; coupe et lève si overtravel détecté."""
        try:
            err = self._aps.get_last_error()
        except Exception as e:                       # liaison série KO
            self._log(f"[banc] lecture GES impossible : {e}")
            return
        if err and "Overtravel" in err:
            self._safe_shutdown()
            raise TestBenchAborted(f"OVERTRAVEL détecté ({err}) — séquence stoppée.")

    def _safe_shutdown(self):
        """Coupe la sortie du Wavetek (retire l'excitation) sans dropper l'armature."""
        try:
            self._wav.disable_output()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Centrage ZER (procédure statique + vérification dynamique)
    # ──────────────────────────────────────────────────────────────────

    def center_zero(self, settle_s: float = 3.0) -> int:
        """
        Centrage statique : démarre le contrôleur sans signal, lit l'asymétrie
        de position via PMA?/PMI? et ajuste ZER pour symétriser.

        Returns la valeur ZER finale.
        """
        self._log("[banc] centrage ZER (statique, sans signal)…")
        self._safe_shutdown()
        self._aps.set_zero_position(0)
        self._aps.start()
        self._aps_started = True
        time.sleep(settle_s)

        pmax = self._aps.get_position_max()
        pmin = self._aps.get_position_min()
        asymmetry = (pmax + pmin) / 2.0
        self._log(f"[banc] PMA={pmax} PMI={pmin} asym={asymmetry:.1f}")

        # Correction grossière (les unités PMA/PMI sont en comptes ADC 0..1023)
        if abs(asymmetry) > 5:
            correction = int(-asymmetry / 10)
            correction = max(-99, min(99, correction))
            self._aps.set_zero_position(correction)
            self._zer_value = correction
            self._log(f"[banc] ZER ajusté à {correction}")
        else:
            self._zer_value = 0
            self._log("[banc] déjà centré (ZER=0)")
        return self._zer_value

    # ──────────────────────────────────────────────────────────────────
    # Réglage d'un point de fréquence (stiffness + servo amplitude)
    # ──────────────────────────────────────────────────────────────────

    def _ensure_started(self) -> None:
        """Démarre le contrôleur APS (STA) une fois — sinon l'AC est coupé et
        le shaker ne bouge pas. Le démarrage centre l'armature sur la consigne ZER."""
        if not self._aps_started:
            self._aps.start()
            self._aps_started = True
            self._log(f"[banc] contrôleur APS démarré (STA)")

    def _apply_stiffness(self, freq_hz: float) -> int:
        """Applique la stiffness recommandée et attend la stabilisation (WTR)."""
        stf = sp.stiffness_for_freq(freq_hz)
        self._aps.set_stiffness(stf)
        # Temps de stabilisation : WTR réel = val×10 + 3500 ms
        try:
            wtr = self._aps.get_wait_time_ramping()
            self._settle_s = (wtr * 10 + 3500) / 1000.0
        except Exception:
            self._settle_s = 4.0
        self._log(f"[banc] {freq_hz} Hz : STF={stf}, stabilisation {self._settle_s:.1f}s")
        time.sleep(self._settle_s)
        return stf

    def _servo_amplitude(self, freq_hz: float, target_g: float) -> tuple[float, float]:
        """
        Asservit l'amplitude du Wavetek (Vpp) pour atteindre target_g, mesuré
        en boucle fermée par l'accéléromètre de référence (détection cohérente).

        La chaîne V->g étant ~linéaire, la correction proportionnelle
        vpp *= target/mesuré converge en 1-2 itérations.

        Returns (vpp_final, accel_mesurée_g).
        """
        vpp = self._servo_start_vpp
        measured = 0.0
        for i in range(self._servo_max_iter):
            self._check_stop()
            vpp = max(0.001, min(vpp, self._vpp_max))
            self._wav.set_amplitude(vpp)
            time.sleep(self._settle_s)
            self._check_overtravel()
            measured = self._accel.measure_acceleration_g(
                freq_hz, ref_channel=self._ref_channel)
            if measured <= 1e-9:
                self._log(f"[banc]   iter{i}: aucun signal, Vpp {vpp:.4f}→{vpp*2:.4f}")
                vpp *= 2.0
                continue
            err = (target_g - measured) / target_g
            self._log(f"[banc]   iter{i}: Vpp={vpp:.4f} → {measured:.5f} g "
                      f"(cible {target_g:.5f}, err {err*100:+.1f}%)")
            if abs(err) <= self._servo_tol:
                return vpp, measured
            vpp = vpp * (target_g / measured)
        self._log(f"[banc]   servo non convergé après {self._servo_max_iter} iters")
        return vpp, measured

    def set_frequency_safe(self, freq_hz: float,
                           target_g: float | None = None) -> dict:
        """
        Configure le banc pour vibrer à freq_hz de façon sûre :
        stiffness adaptée + amplitude asservie à la cible, sans overtravel.

        Returns un dict d'état (voir calibration_sweep).
        """
        if target_g is None:
            target_g = self.target_accel_g(freq_hz)

        A = sp.peak_displacement_mm(target_g, freq_hz)
        zer_mm = self.zer_to_mm(self._zer_value)
        margin = sp.safety_margin_mm(freq_hz, target_g, self._stroke, zer_mm)

        result = {
            "freq_hz": freq_hz,
            "target_g": target_g,
            "stiffness": sp.stiffness_for_freq(freq_hz),
            "displacement_mm": A,
            "safety_margin_mm": margin,
            "measured_g": 0.0,
            "vpp": 0.0,
            "safe": margin > 0,
            "skipped": False,
            "note": "",
        }

        # Refus si hors course
        if not sp.is_safe(freq_hz, target_g, self._stroke, zer_mm):
            result["skipped"] = True
            result["note"] = (f"hors course : déplacement {A:.1f}mm + ZER {zer_mm:.1f}mm "
                              f"> stroke {self._stroke}mm")
            self._log(f"[banc] {freq_hz} Hz IGNORÉ — {result['note']}")
            return result

        # Refus si sous le plancher utile
        if target_g < self._floor:
            result["skipped"] = True
            result["note"] = f"cible {target_g:.5f} g < plancher {self._floor} g"
            self._log(f"[banc] {freq_hz} Hz IGNORÉ — {result['note']}")
            return result

        self._check_stop()
        self._ensure_started()          # contrôleur en marche (sinon AC coupé)
        self._apply_stiffness(freq_hz)
        self._wav.set_frequency(freq_hz)
        self._wav.enable_output()
        vpp, measured = self._servo_amplitude(freq_hz, target_g)
        result["vpp"] = vpp
        result["measured_g"] = measured
        return result

    # ──────────────────────────────────────────────────────────────────
    # Étape 1 : plancher de bruit + fonction de transfert du banc H_banc(f)
    # ──────────────────────────────────────────────────────────────────

    def measure_noise_floor(self, duration_s: float = 60.0) -> float:
        """
        Plancher de bruit (g RMS) : shaker arrêté, ampli allumé.
        Sert au calcul du SNR par point de calibration.
        """
        self._log(f"[banc] plancher de bruit ({duration_s:.0f}s, shaker arrêté)…")
        self._safe_shutdown()
        floor = self._accel.measure_noise_floor(duration_s,
                                                ref_channel=self._ref_channel)
        self._noise_floor_g = floor
        self._log(f"[banc] plancher de bruit = {floor:.6g} g RMS")
        return floor

    def measure_bench_transfer(self, freqs, on_point=None) -> list[dict]:
        """
        Étape 1 de la calibration : fonction de transfert du banc

            H_banc(f) = a_table(f) / V_wavetek(f)   [g/V]

        Pour chaque fréquence : réglage sûr (enveloppe + stiffness + servo),
        puis mesure de l'accélération de référence, du SNR et de la THD.
        Stocke H_banc dans self._h_bench (accessible via bench_transfer()).

        Lève TestBenchAborted sur overtravel / arrêt utilisateur.
        """
        results = []
        try:
            for freq in freqs:
                self._check_stop()
                res = self.set_frequency_safe(freq)
                if not res["skipped"]:
                    m = self._accel.measure(freq, ref_channel=self._ref_channel)
                    res["measured_g"] = m["accel_g"]
                    res["snr_db"] = m["snr_db"]
                    res["thd_percent"] = m["thd_percent"]
                    res["h_bench_g_per_v"] = (m["accel_g"] / res["vpp"]
                                              if res["vpp"] > 1e-9 else 0.0)
                    self._h_bench[freq] = res["h_bench_g_per_v"]
                    if m["snr_db"] < SNR_MIN_DB:
                        res["note"] = (f"SNR {m['snr_db']:.1f} dB < {SNR_MIN_DB} dB")
                    self._log(f"[banc] {freq} Hz : H_banc={res['h_bench_g_per_v']:.4g} g/V, "
                              f"SNR={m['snr_db']:.1f} dB, THD={m['thd_percent']:.2f}%")
                results.append(res)
                if on_point is not None:
                    on_point(res)
        finally:
            self._safe_shutdown()
        return results

    def bench_transfer(self) -> dict:
        """Retourne la dernière fonction de transfert du banc {freq: g/V}."""
        return dict(self._h_bench)

    # ──────────────────────────────────────────────────────────────────
    # Linéarité (3 niveaux × N fréquences)
    # ──────────────────────────────────────────────────────────────────

    def measure_linearity(self, freqs, levels=(0.25, 0.5, 1.0),
                          geophone_count: int = 1024,
                          geophone_rate: int = 1000,
                          on_point=None) -> list[dict]:
        """
        Linéarité : à chaque fréquence, mesure la sensibilité géophone à
        plusieurs niveaux d'amplitude (fractions de la cible). L'erreur de
        linéarité = 20·log10(max/min) des sensibilités ; tolérance
        CAL_LINEARITY_MAX_DB. Requiert l'ADS1285 (géophone).

        Returns une liste de dicts {freq_hz, levels:[...], linearity_error_db, pass}.
        Lève TestBenchAborted sur overtravel / arrêt.
        """
        results = []
        try:
            for freq in freqs:
                self._check_stop()
                base = self.target_accel_g(freq)
                per_level = []
                for lvl in levels:
                    self._check_stop()
                    res = self.set_frequency_safe(freq, base * lvl)
                    pt = {"freq_hz": freq, "level": lvl, "target_g": base * lvl,
                          "skipped": res["skipped"], "note": res.get("note", ""),
                          "measured_g": res.get("measured_g", 0.0),
                          "sensitivity_counts_per_g": 0.0}
                    if not res["skipped"]:
                        # Accéléro + géophone en parallèle (même fenêtre)
                        m, amp = self._measure_synced(freq, geophone_count, geophone_rate)
                        pt["measured_g"] = m["accel_g"]
                        if amp is not None and m["accel_g"] > 1e-9:
                            pt["sensitivity_counts_per_g"] = amp / m["accel_g"]
                    per_level.append(pt)
                err = linearity_error_db([p["sensitivity_counts_per_g"]
                                          for p in per_level])
                entry = {"freq_hz": freq, "levels": per_level,
                         "linearity_error_db": err,
                         "pass": err <= CAL_LINEARITY_MAX_DB}
                results.append(entry)
                self._log(f"[banc] linéarité {freq} Hz : {err:.2f} dB "
                          f"({'OK' if entry['pass'] else 'HORS TOL'})")
                if on_point is not None:
                    on_point(entry)
        finally:
            self._safe_shutdown()
        return results

    # ──────────────────────────────────────────────────────────────────
    # Vérification quotidienne (H_banc vs référence à 1/10/50 Hz)
    # ──────────────────────────────────────────────────────────────────

    def daily_verification(self, reference: dict, freqs=None,
                           on_point=None) -> list[dict]:
        """
        Mesure H_banc aux fréquences de contrôle et compare à une référence
        {freq: g/V}. Écart en dB par fréquence ; dérive si |écart| > CAL_DAILY_TOL_DB.

        reference : dict avec clés float ou str (tolérant aux deux).
        """
        if freqs is None:
            freqs = list(CAL_DAILY_FREQS_HZ)
        results = []
        try:
            for freq in freqs:
                self._check_stop()
                res = self.set_frequency_safe(freq)
                if not res["skipped"]:
                    m = self._accel.measure(freq, ref_channel=self._ref_channel)
                    h = m["accel_g"] / res["vpp"] if res["vpp"] > 1e-9 else 0.0
                    ref = reference.get(freq, reference.get(str(freq)))
                    dev = ratio_db(h, ref) if ref else float("nan")
                    res["h_bench_g_per_v"] = h
                    res["h_bench_ref"] = ref
                    res["deviation_db"] = dev
                    res["pass"] = (ref is not None and abs(dev) <= CAL_DAILY_TOL_DB)
                    self._log(f"[banc] vérif {freq} Hz : {dev:+.2f} dB vs réf "
                              f"({'OK' if res['pass'] else 'DERIVE'})")
                results.append(res)
                if on_point is not None:
                    on_point(res)
        finally:
            self._safe_shutdown()
        return results

    # ──────────────────────────────────────────────────────────────────
    # Mesure synchronisée accéléromètre + géophone (même fenêtre)
    # ──────────────────────────────────────────────────────────────────

    def _measure_synced(self, freq_hz: float,
                        geophone_count: int, geophone_rate: int):
        """
        Acquiert l'accéléromètre de référence (g + SNR + THD) ET le géophone
        EN PARALLÈLE, pour qu'ils couvrent la même tranche d'excitation.

        Retourne (m_accel: dict, geophone_amp: float | None).
        """
        holder = {"m": None, "exc": None}

        def _acq_accel():
            try:
                holder["m"] = self._accel.measure(
                    freq_hz, ref_channel=self._ref_channel)
            except Exception as e:               # capturée -> re-levée après join
                holder["exc"] = e

        th = threading.Thread(target=_acq_accel)
        th.start()
        samples = None
        try:
            if self._ads is not None:
                samples = self._ads.acquire(geophone_count, geophone_rate)
        finally:
            th.join()
        if holder["exc"] is not None:
            raise holder["exc"]
        amp = (coherent_amplitude_peak(samples, freq_hz, geophone_rate)
               if samples is not None else None)
        return holder["m"], amp

    # ──────────────────────────────────────────────────────────────────
    # Étape 2 : sweep de calibration géophone
    # ──────────────────────────────────────────────────────────────────

    def calibration_sweep(self, freqs,
                          geophone_count: int = 1024,
                          geophone_rate: int = 1000,
                          on_point=None) -> list[dict]:
        """
        Sweep de calibration : pour chaque fréquence, règle le banc en sécurité,
        acquiert la réponse du géophone (si ADS1285 fourni) et calcule sa
        sensibilité (amplitude géophone / accélération mesurée).

        Parameters
        ----------
        freqs : itérable de fréquences (Hz)
        geophone_count, geophone_rate : params d'acquisition ADS1285
        on_point : callback(result_dict) appelé après chaque fréquence

        Returns la liste des dicts de résultat.

        Lève TestBenchAborted en cas d'overtravel ou d'arrêt utilisateur ;
        la sortie Wavetek est coupée avant de lever.
        """
        results = []
        try:
            for freq in freqs:
                self._check_stop()
                res = self.set_frequency_safe(freq)

                if not res["skipped"]:
                    # Accéléro + géophone EN PARALLÈLE (même fenêtre d'excitation)
                    m, amp = self._measure_synced(freq, geophone_count, geophone_rate)
                    res["measured_g"] = m["accel_g"]
                    res["snr_db"] = m["snr_db"]
                    res["thd_percent"] = m["thd_percent"]
                    if m["snr_db"] < SNR_MIN_DB:
                        res["note"] = f"SNR {m['snr_db']:.1f} dB < {SNR_MIN_DB} dB"

                    if amp is not None:
                        res["geophone_counts_peak"] = amp
                        res["sensitivity_counts_per_g"] = (
                            amp / res["measured_g"] if res["measured_g"] > 1e-9 else 0.0)

                results.append(res)
                if on_point is not None:
                    on_point(res)
        finally:
            # Toujours retirer l'excitation à la fin du sweep
            self._safe_shutdown()
        return results
