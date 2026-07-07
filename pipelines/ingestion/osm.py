"""Ingestion des points d'intérêt OpenStreetMap (API Overpass) → bronze.

Trois catégories utiles au score d'investissement :
- education : écoles, crèches, collèges/lycées, universités
- transport : gares, arrêts de tram, arrêts de bus
- commerce  : supermarchés, supérettes, boulangeries, centres commerciaux, marchés

On interroge nodes + ways + relations (`nwr`) avec `out center` : les
bâtiments dessinés en polygone ressortent avec leur centroïde.

Sortie : data/bronze/osm/departement={dep}/pois.parquet
"""

import json
import logging
import re
from pathlib import Path

import pandas as pd

from pipelines.common import already_ingested, atomic_write_parquet, http_get, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.osm")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM évolue en continu : rafraîchissement hebdomadaire
FRAICHEUR_JOURS = 7

# (catégorie, clé OSM, regex de valeurs)
POI_FILTERS = [
    ("education", "amenity", "^(school|kindergarten|college|university)$"),
    ("transport", "railway", "^(station|tram_stop)$"),
    ("transport", "highway", "^(bus_stop)$"),
    ("commerce", "shop", "^(supermarket|convenience|bakery|mall|department_store)$"),
    ("commerce", "amenity", "^(marketplace)$"),
]


def build_query(dep: str) -> str:
    """Requête Overpass QL : tous les POI ciblés dans le département (zone ISO)."""
    clauses = "\n".join(
        f'  nwr["{key}"~"{regex}"](area.dep);' for _, key, regex in POI_FILTERS
    )
    return (
        '[out:json][timeout:180];\n'
        f'area["ISO3166-2"="FR-{dep}"][admin_level=6]->.dep;\n'
        f'(\n{clauses}\n);\n'
        'out center tags;'
    )


def categorize(tags: dict) -> str | None:
    """Retrouve la catégorie d'un élément à partir de ses tags OSM."""
    for category, key, regex in POI_FILTERS:
        value = tags.get(key)
        if value and re.match(regex, value):
            return category
    return None


def elements_to_rows(elements: list[dict]) -> list[dict]:
    """Aplatit les éléments Overpass : coordonnées (directes ou centroïde) + tags."""
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        center = el.get("center", {})
        lat = el.get("lat", center.get("lat"))
        lon = el.get("lon", center.get("lon"))
        if lat is None or lon is None:
            continue
        rows.append({
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
            "categorie": categorize(tags),
            "nom": tags.get("name"),
            "latitude": lat,
            "longitude": lon,
            # Bronze : on garde tous les tags bruts pour ne rien perdre
            "tags": json.dumps(tags, ensure_ascii=False),
        })
    return rows


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    produced: list[Path] = []
    for dep in departements:
        query = build_query(dep)
        source = f"{OVERPASS_URL} FR-{dep}"
        out = BRONZE_DIR / "osm" / f"departement={dep}" / "pois.parquet"
        if already_ingested(out, source=source, force=force, max_age_jours=FRAICHEUR_JOURS):
            produced.append(out)
            continue
        resp = http_get(OVERPASS_URL, params={"data": query}, timeout=300)
        elements = resp.json().get("elements", [])
        df = pd.DataFrame(elements_to_rows(elements))
        atomic_write_parquet(df, out)
        write_manifest(out, source=source, rows=len(df), extra={"departement": dep, "query": query})
        logger.info("OSM %s : %d POI → %s", dep, len(df), out)
        produced.append(out)
    return produced
