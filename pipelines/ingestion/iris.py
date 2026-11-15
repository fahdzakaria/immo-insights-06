"""Ingestion des contours IRIS (quartiers INSEE) → bronze.

Les IRIS sont le découpage infra-communal officiel de l'INSEE (≈ 2 000
habitants par quartier dans les communes de plus de 10 000 habitants ; les
petites communes forment un seul IRIS de type « Z »). L'IGN les diffuse sous
le nom « Contours... IRIS® », en Licence Ouverte 2.0 (Etalab).

Source : service WFS de la Géoplateforme IGN, couche
`STATISTICALUNITS.IRIS:contours_iris`, filtrée sur le département — on évite
ainsi l'archive nationale (plusieurs centaines de Mo) pour quelques centaines
de polygones.

Bronze = brut : une ligne par IRIS, la géométrie est conservée telle que
reçue (GeoJSON en texte, WGS84). Le point-dans-polygone se fait en silver.

Sortie : data/bronze/iris/departement={dep}/contours.parquet
"""

import json
import logging
from pathlib import Path

import pandas as pd

from pipelines.common import already_ingested, atomic_write_parquet, http_get, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.iris")

WFS_URL = "https://data.geopf.fr/wfs/ows"
COUCHE = "STATISTICALUNITS.IRIS:contours_iris"
LICENCE = "Licence Ouverte 2.0 (Etalab) — IGN / INSEE, Contours... IRIS®"

# Les contours ne changent qu'une fois par an (nouveau millésime) : un
# rafraîchissement mensuel suffit largement.
FRAICHEUR_JOURS = 30

TAILLE_PAGE = 1000
# Garde-fou anti-boucle : aucun département ne dépasse quelques milliers d'IRIS
MAX_PAGES = 50

PROPRIETES_ATTENDUES = {"code_iris", "nom_iris", "code_insee", "nom_commune", "type_iris"}


def build_params(dep: str, start_index: int = 0) -> dict:
    """Paramètres WFS 2.0 : GeoJSON en WGS84, filtré sur le département, paginé.

    Le tri sur `code_iris` rend la pagination stable (sans tri, le serveur ne
    garantit pas l'ordre d'une page à l'autre).
    """
    return {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": COUCHE,
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "CQL_FILTER": f"code_insee LIKE '{dep}%'",
        "SORTBY": "code_iris",
        "COUNT": TAILLE_PAGE,
        "STARTINDEX": start_index,
    }


def features_to_rows(features: list[dict]) -> list[dict]:
    """Aplatit les features GeoJSON. Échoue clairement si le schéma a changé."""
    rows = []
    for f in features:
        props = f.get("properties") or {}
        manquantes = PROPRIETES_ATTENDUES - set(props)
        if manquantes:
            raise ValueError(
                f"Format IRIS inattendu : propriétés absentes {sorted(manquantes)} "
                f"(reçu : {sorted(props)})"
            )
        geometrie = f.get("geometry")
        if not geometrie or geometrie.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"IRIS {props['code_iris']} : géométrie absente ou non surfacique")
        rows.append({
            "code_iris": str(props["code_iris"]),
            "nom_iris": props["nom_iris"],
            "code_commune": str(props["code_insee"]),
            "nom_commune": props["nom_commune"],
            "type_iris": props["type_iris"],
            "id_ign": props.get("cleabs"),
            "geometrie_geojson": json.dumps(geometrie, separators=(",", ":")),
        })
    return rows


def telecharger(dep: str) -> list[dict]:
    """Récupère tous les IRIS du département, page par page, et contrôle la complétude."""
    rows: list[dict] = []
    attendu = None
    for page in range(MAX_PAGES):
        payload = http_get(WFS_URL, params=build_params(dep, page * TAILLE_PAGE), timeout=120).json()
        features = payload.get("features", [])
        if attendu is None:
            attendu = payload.get("numberMatched")
        rows.extend(features_to_rows(features))
        if len(features) < TAILLE_PAGE:
            break
    else:
        raise RuntimeError(f"IRIS {dep} : plus de {MAX_PAGES} pages, pagination suspecte")

    if not rows:
        raise ValueError(f"IRIS {dep} : aucun contour renvoyé par le WFS")
    if isinstance(attendu, int) and attendu != len(rows):
        raise ValueError(f"IRIS {dep} : {len(rows)} contours reçus pour {attendu} annoncés")
    codes = [r["code_iris"] for r in rows]
    if len(set(codes)) != len(codes):
        raise ValueError(f"IRIS {dep} : codes IRIS en double (pagination instable ?)")
    return rows


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    produced: list[Path] = []
    for dep in departements:
        source = f"{WFS_URL} {COUCHE} {dep}"
        out = BRONZE_DIR / "iris" / f"departement={dep}" / "contours.parquet"
        if already_ingested(out, source=source, force=force, max_age_jours=FRAICHEUR_JOURS):
            produced.append(out)
            continue
        df = pd.DataFrame(telecharger(dep)).sort_values("code_iris", ignore_index=True)
        atomic_write_parquet(df, out)
        write_manifest(out, source=source, rows=len(df), extra={
            "departement": dep,
            "licence": LICENCE,
            "communes": int(df["code_commune"].nunique()),
            "types_iris": df["type_iris"].value_counts().to_dict(),
        })
        logger.info("IRIS %s : %d contours (%d communes) → %s",
                    dep, len(df), df["code_commune"].nunique(), out)
        produced.append(out)
    return produced
