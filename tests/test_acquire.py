"""
Script de test d'acquisition ADS1285.

Usage :
    python test_acquire.py [options]

Options :
    --rate   RATE    Taux d'échantillonnage en Hz (4000, 2000, 1000, 500, 250)
                     Défaut : ADS1285_SAMPLE_RATE dans settings.py
    --count  N       Nombre d'échantillons (puissance de 2 : 256, 512, 1024, ...)
                     Défaut : ADS1285_NUM_SAMPLES dans settings.py
    --out    PATH    Fichier de sortie (.csv ou .npy)
                     Défaut : data/ads1285_YYYYMMDD_HHMMSS.csv

Exemples :
    python test_acquire.py
    python test_acquire.py --rate 1000 --count 2048
    python test_acquire.py --rate 500 --count 4096 --out mesure.csv
"""

import argparse
import csv
import os
import time

from config.settings import (
    ADS1285_SAMPLE_RATE,
    ADS1285_NUM_SAMPLES,
    DATA_OUTPUT_DIR,
)
from equipment.ads1285 import ADS1285

VALID_RATES = {4000, 2000, 1000, 500, 250}


def parse_args():
    parser = argparse.ArgumentParser(description="Acquisition ADS1285 EVM")
    parser.add_argument("--rate", type=int, default=ADS1285_SAMPLE_RATE,
                        choices=sorted(VALID_RATES),
                        help=f"Taux d'échantillonnage Hz (défaut : {ADS1285_SAMPLE_RATE})")
    parser.add_argument("--count", type=int, default=ADS1285_NUM_SAMPLES,
                        help=f"Nombre d'échantillons (défaut : {ADS1285_NUM_SAMPLES})")
    parser.add_argument("--out", type=str, default=None,
                        help="Fichier de sortie (.csv ou .npy)")
    return parser.parse_args()


def default_output_path(ext="csv"):
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(DATA_OUTPUT_DIR, f"ads1285_{ts}.{ext}")


def save_csv(path: str, samples: list[int], sample_rate: int):
    dt = 1.0 / sample_rate
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "time_s", "value"])
        for i, v in enumerate(samples):
            writer.writerow([i, f"{i * dt:.9f}", v])
    print(f"  Sauvegardé : {path}  ({len(samples)} lignes)")


def save_npy(path: str, samples: list[int]):
    import numpy as np
    arr = np.array(samples, dtype=np.int32)
    np.save(path, arr)
    print(f"  Sauvegardé : {path}  (shape={arr.shape}, dtype={arr.dtype})")


def main():
    args = parse_args()

    out_path = args.out
    use_npy = out_path is not None and out_path.endswith(".npy")

    if out_path is None:
        out_path = default_output_path("csv")

    print(f"Paramètres : rate={args.rate} Hz  count={args.count}")
    print(f"Durée estimée : {args.count / args.rate:.2f} s")
    print()

    with ADS1285(sample_rate=args.rate, num_samples=args.count) as ads:
        print(f"Acquisition de {args.count} échantillons à {args.rate} Hz...")
        t0 = time.perf_counter()
        samples = ads.acquire()
        elapsed = time.perf_counter() - t0

    print(f"  {len(samples)} échantillons reçus en {elapsed:.2f} s")
    if samples:
        print(f"  min={min(samples)}  max={max(samples)}  moyenne={sum(samples)/len(samples):.1f}")
        print(f"  premier={samples[0]}  dernier={samples[-1]}")
    print()

    if use_npy:
        save_npy(out_path, samples)
    else:
        save_csv(out_path, samples, args.rate)


if __name__ == "__main__":
    main()
