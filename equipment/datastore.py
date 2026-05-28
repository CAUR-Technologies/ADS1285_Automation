"""
Sauvegarde automatique des donnees d'acquisition et de calibration.

Chaque execution ecrit dans DATA_OUTPUT_DIR un fichier nomme selon le cas,
horodate comme le journal (logs/bench_<date>_<heure>.log) :

    <cas>[_<geophone>][_<axe>]_<AAAA-MM-JJ_HH-MM-SS>.<ext>

Exemples :
    acquisition_HG-5VHS_2026-05-28_13-05-12.csv
    balayage_HG-5VHS_vertical_2026-05-28_13-05-12.csv
    transfert_banc_vertical_2026-05-28_13-05-12.csv
"""

import os
import re
from datetime import datetime

from config.settings import DATA_OUTPUT_DIR


def timestamp() -> str:
    """Horodatage de fichier, meme convention que le journal."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _slug(text) -> str:
    """Nettoie un fragment de nom de fichier (geophone, axe)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text).strip())
    return s.strip("-")


def build_path(case: str, ext: str, *, geophone=None, axis=None,
               ts: str | None = None) -> str:
    """Construit (et garantit le dossier de) un chemin de fichier horodate.

    case     : identifiant du cas (acquisition, balayage, ...)
    ext      : extension sans point (csv, npz)
    geophone : modele de geophone a inclure dans le nom (optionnel)
    axis     : axe (vertical/horizontal) a inclure dans le nom (optionnel)
    ts       : horodatage partage (sinon genere maintenant) — permet a un
               CSV et un NPZ d'une meme execution de porter le meme suffixe.
    """
    parts = [_slug(case)]
    if geophone:
        parts.append(_slug(geophone))
    if axis:
        parts.append(_slug(axis))
    parts.append(ts or timestamp())
    fname = "_".join(parts) + "." + ext.lstrip(".")
    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    return os.path.join(DATA_OUTPUT_DIR, fname)


def _fmt(value) -> str:
    """Formate une valeur pour le CSV (floats compacts, virgules echappees)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace(",", ";")


def write_csv(path: str, columns, rows, header_comments=None) -> str:
    """Ecrit un CSV : lignes de commentaire `# ...`, en-tete, puis donnees.

    columns : liste des noms de colonnes
    rows    : iterable de lignes (chaque ligne = iterable de valeurs)
    """
    with open(path, "w", encoding="utf-8") as f:
        for line in (header_comments or []):
            f.write(f"# {line}\n")
        f.write(",".join(columns) + "\n")
        for row in rows:
            f.write(",".join(_fmt(v) for v in row) + "\n")
    return path
