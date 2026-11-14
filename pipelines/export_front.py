"""Export des marts gold en JSON pour le frontend (mode « statique »).

Les 5 marts gold pèsent ~150 Ko en Parquet (~570 Ko en JSON, ~90 Ko compressés) : le site peut les embarquer et
faire tout le filtrage dans le navigateur, sans API à héberger ni à réveiller.
Ce module écrit un fichier JSON par mart + un `meta.json` (date de
génération, volumétrie, période couverte) dans `frontend/public/data/`.

Le format est « colonnes » ({"colonnes": [...], "lignes": [[...], ...]}) :
deux à trois fois plus compact qu'une liste d'objets, reconstruit côté front.

Usage : python -m pipelines.export_front [--out DOSSIER]
"""

import argparse
import json
import logging
import math
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from pipelines.config import DATA_DIR, GOLD_DIR

logger = logging.getLogger("export_front")

MARTS = [
    "mart_prix_m2_par_commune",
    "mart_evolution_trimestrielle",
    "mart_rendement_locatif",
    "mart_impact_dpe",
    "mart_score_investissement",
]


def front_data_dir() -> Path:
    """Dossier de sortie : FRONT_DATA_DIR (frontend/public/data, via le montage de frontend/public)."""
    return Path(os.environ.get("FRONT_DATA_DIR", DATA_DIR / "front"))


def _json_ready(valeur):
    """NaN/inf → null (JSON strict) ; entiers stockés en float → int ; autres types → texte."""
    if valeur is None:
        return None
    if isinstance(valeur, Decimal):
        valeur = float(valeur)  # sinon le front recevrait du texte et l'exclurait des filtres
    if isinstance(valeur, (date, datetime)):
        return valeur.isoformat()
    if isinstance(valeur, float):
        if math.isnan(valeur) or math.isinf(valeur):
            return None
        # 6 décimales : gomme le bruit flottant des moyennes (lat/lon à 1e-14 près
        # d'un run à l'autre) → fichiers identiques tant que la donnée ne change pas
        valeur = round(valeur, 6)
        return int(valeur) if valeur.is_integer() else valeur
    if isinstance(valeur, (int, str, bool)):
        return valeur
    return str(valeur)


def lire_mart(chemin: Path) -> dict:
    """Parquet → {"colonnes": [...], "lignes": [[...]]}, trié pour un diff git stable."""
    cur = duckdb.connect(":memory:").execute(f"SELECT * FROM read_parquet('{chemin}') ORDER BY ALL")
    colonnes = [d[0] for d in cur.description]
    lignes = [[_json_ready(v) for v in ligne] for ligne in cur.fetchall()]
    return {"colonnes": colonnes, "lignes": lignes}


def _serialiser(objet: dict) -> str:
    return json.dumps(objet, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _ecrire(texte: str, chemin: Path) -> None:
    """Écriture atomique (tmp + rename), toujours en UTF-8."""
    tmp = chemin.with_suffix(".json.tmp")
    tmp.write_text(texte, encoding="utf-8")
    tmp.replace(chemin)


# Deux exports de la même donnée peuvent différer de 0,000001 sur une moyenne
# (latitude/longitude : l'agrégation parallèle de DuckDB n'additionne pas dans
# le même ordre, et l'arrondi à 6 décimales bascule parfois). Ce n'est pas un
# changement : on tolère un écart juste au-dessus d'une unité d'arrondi.
TOLERANCE_FLOTTANT = 1.5e-6


def _meme_donnee(chemin: Path, table: dict) -> bool:
    """Le JSON déjà exporté contient-il la même donnée, au bruit flottant près ?"""
    if not chemin.exists():
        return False
    try:
        ancien = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(ancien, dict):
        return False
    if ancien.get("colonnes") != table["colonnes"] or len(ancien.get("lignes", [])) != len(table["lignes"]):
        return False
    for ligne_a, ligne_b in zip(ancien["lignes"], table["lignes"]):
        for a, b in zip(ligne_a, ligne_b):
            if a == b:
                continue
            nombres = (isinstance(a, (int, float)) and isinstance(b, (int, float))
                       and not isinstance(a, bool) and not isinstance(b, bool))
            if not nombres or abs(a - b) > TOLERANCE_FLOTTANT:
                return False
    return True


def exporter(gold_dir: Path | None = None, out_dir: Path | None = None) -> Path:
    """Écrit les JSON du front ; échoue si un mart manque ou est vide."""
    gold_dir = Path(gold_dir or GOLD_DIR)
    out_dir = Path(out_dir or front_data_dir())
    out_dir.mkdir(parents=True, exist_ok=True)

    volumetrie: dict[str, int] = {}
    tables: dict[str, dict] = {}
    for mart in MARTS:
        src = gold_dir / f"{mart}.parquet"
        if not src.exists():
            raise FileNotFoundError(f"Mart gold absent : {src} (lancer dbt run d'abord)")
        table = lire_mart(src)
        if not table["lignes"]:
            raise ValueError(f"Mart gold vide : {src} — export annulé pour ne pas publier un site vide")
        tables[mart] = table
        volumetrie[mart] = len(table["lignes"])

    # Donnée inchangée depuis le dernier export → on ne touche à rien : la date
    # du pied de page reste celle du dernier vrai changement, et git reste propre.
    textes = {mart: _serialiser(table) for mart, table in tables.items()}
    inchange = (out_dir / "meta.json").exists() and all(
        _meme_donnee(out_dir / f"{mart}.json", table) for mart, table in tables.items()
    )
    if inchange:
        logger.info("Export front : marts inchangés, rien à réécrire dans %s", out_dir)
        return out_dir

    # On n'écrit qu'une fois TOUS les marts validés : jamais d'export à moitié fait
    for mart, texte in textes.items():
        _ecrire(texte, out_dir / f"{mart}.json")

    evo = tables["mart_evolution_trimestrielle"]
    i_trim = evo["colonnes"].index("trimestre")
    trimestres = sorted({ligne[i_trim] for ligne in evo["lignes"]})
    meta = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "premier_trimestre": trimestres[0],
        "dernier_trimestre": trimestres[-1],
        "lignes": volumetrie,
    }
    _ecrire(_serialiser(meta), out_dir / "meta.json")
    logger.info("Export front : %s → %s", volumetrie, out_dir)
    return out_dir


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="dossier de sortie")
    exporter(out_dir=parser.parse_args().out)
