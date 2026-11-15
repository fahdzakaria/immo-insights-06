"""Export des marts gold en JSON pour le frontend (mode « statique »).

Les 6 marts gold pèsent ~150 Ko en Parquet (~570 Ko en JSON, ~90 Ko compressés) : le site peut les embarquer et
faire tout le filtrage dans le navigateur, sans API à héberger ni à réveiller.
Ce module écrit un fichier JSON par mart + un `meta.json` (date de
génération, volumétrie, période couverte) dans `frontend/public/data/`.

Le format est « colonnes » ({"colonnes": [...], "lignes": [[...], ...]}) :
deux à trois fois plus compact qu'une liste d'objets, reconstruit côté front.

Les contours des quartiers IRIS présents dans `mart_prix_m2_par_quartier` sont
exportés à part, allégés, dans `frontend/public/geo/iris-{dep}.geojson` : la
carte ne les charge qu'au zoom.

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

from pipelines.config import BRONZE_DIR, DATA_DIR, GOLD_DIR

logger = logging.getLogger("export_front")

MARTS = [
    "mart_prix_m2_par_commune",
    "mart_prix_m2_par_quartier",
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


# 5 décimales de degré ≈ 1 m : invisible sur la carte, 40 % de poids en moins
DECIMALES_CONTOURS = 5


def _alleger_anneau(anneau: list) -> list:
    """Arrondit les sommets d'un anneau et retire les doublons consécutifs créés par l'arrondi."""
    points: list[list[float]] = []
    for lon, lat, *_ in anneau:
        p = [round(lon, DECIMALES_CONTOURS), round(lat, DECIMALES_CONTOURS)]
        if not points or p != points[-1]:
            points.append(p)
    return points


def alleger_geometrie(geometrie: dict) -> dict:
    """Polygon / MultiPolygon GeoJSON → même géométrie, coordonnées arrondies.

    Un anneau réduit à moins de 4 points par l'arrondi (éclat de quelques
    mètres) n'est plus valide : si c'est l'anneau EXTÉRIEUR, tout le polygone
    disparaît (sinon son premier trou deviendrait un faux extérieur) ; si c'est
    un trou, seul le trou disparaît. Une géométrie qui deviendrait vide échoue.
    """
    def polygone(anneaux: list) -> list:
        allege = [_alleger_anneau(a) for a in anneaux]
        if not allege or len(allege[0]) < 4:
            return []
        return [allege[0]] + [a for a in allege[1:] if len(a) >= 4]

    if geometrie["type"] == "Polygon":
        polygones = [polygone(geometrie["coordinates"])]
    else:
        polygones = [polygone(p) for p in geometrie["coordinates"]]
    polygones = [p for p in polygones if p]
    if not polygones:
        raise ValueError("Contour IRIS vide après allègement (polygone de moins d'un mètre ?)")
    if geometrie["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": polygones[0]}
    return {"type": "MultiPolygon", "coordinates": polygones}


def contours_quartiers(table: dict, bronze_dir: Path) -> dict[str, dict]:
    """GeoJSON allégé des quartiers du mart, un FeatureCollection par département.

    Seuls les quartiers présents dans le mart sont exportés (communes découpées
    en IRIS). Un quartier du mart sans contour est une incohérence : on échoue.
    """
    i_iris, i_dep = table["colonnes"].index("code_iris"), table["colonnes"].index("code_departement")
    par_dep: dict[str, set[str]] = {}
    for ligne in table["lignes"]:
        par_dep.setdefault(ligne[i_dep], set()).add(ligne[i_iris])

    sorties = {}
    for dep, codes in sorted(par_dep.items()):
        src = bronze_dir / "iris" / f"departement={dep}" / "contours.parquet"
        if not src.exists():
            raise FileNotFoundError(f"Contours IRIS absents : {src} (lancer l'ingestion iris d'abord)")
        lignes = duckdb.connect(":memory:").execute(
            f"SELECT code_iris, nom_iris, code_commune, nom_commune, geometrie_geojson "
            f"FROM read_parquet('{src}') ORDER BY code_iris").fetchall()
        features = [
            {"type": "Feature",
             "properties": {"code": code, "nom": nom, "commune": commune, "nom_commune": nom_commune},
             "geometry": alleger_geometrie(json.loads(geometrie))}
            for code, nom, commune, nom_commune, geometrie in lignes if code in codes
        ]
        manquants = codes - {f["properties"]["code"] for f in features}
        if manquants:
            raise ValueError(f"Quartiers du mart sans contour IRIS ({dep}) : {sorted(manquants)[:5]}")
        sorties[dep] = {"type": "FeatureCollection", "features": features}
    return sorties


def exporter_contours(table: dict, bronze_dir: Path, geo_dir: Path) -> list[Path]:
    """Écrit geo/iris-{dep}.geojson ; ne réécrit pas un fichier identique."""
    geo_dir.mkdir(parents=True, exist_ok=True)
    chemins = []
    for dep, collection in contours_quartiers(table, bronze_dir).items():
        chemin = geo_dir / f"iris-{dep}.geojson"
        texte = _serialiser(collection)
        if not chemin.exists() or chemin.read_text(encoding="utf-8") != texte:
            _ecrire(texte, chemin)
            logger.info("Export front : %d contours de quartiers → %s (%d Ko)",
                        len(collection["features"]), chemin, len(texte.encode()) // 1024)
        chemins.append(chemin)
    return chemins


def exporter(gold_dir: Path | None = None, out_dir: Path | None = None,
             bronze_dir: Path | None = None) -> Path:
    """Écrit les JSON du front ; échoue si un mart manque ou est vide."""
    gold_dir = Path(gold_dir or GOLD_DIR)
    out_dir = Path(out_dir or front_data_dir())
    bronze_dir = Path(bronze_dir or BRONZE_DIR)
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

    # Contours des quartiers : fichier à part (public/geo, à côté de public/data),
    # géré indépendamment des marts — il ne change qu'avec le millésime IRIS.
    exporter_contours(tables["mart_prix_m2_par_quartier"], bronze_dir, out_dir.parent / "geo")

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
