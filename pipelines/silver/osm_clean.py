"""Silver OSM : POI dédoublonnés avec catégorie et coordonnées garanties.

Sortie : data/silver/osm/departement={dep}/pois.parquet
"""

import logging
from pathlib import Path

import pandas as pd

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import BRONZE_DIR, SILVER_DIR

logger = logging.getLogger("silver.osm")


def build(departements: list[str]) -> list[Path]:
    produced = []
    for dep in departements:
        src = BRONZE_DIR / "osm" / f"departement={dep}" / "pois.parquet"
        df = pd.read_parquet(src)
        avant = len(df)
        df = df[df["categorie"].notna() & df["latitude"].notna() & df["longitude"].notna()]
        df = df.drop_duplicates(subset=["osm_type", "osm_id"])
        df = df[["osm_type", "osm_id", "categorie", "nom", "latitude", "longitude"]]

        out = SILVER_DIR / "osm" / f"departement={dep}" / "pois.parquet"
        atomic_write_parquet(df, out)
        write_manifest(out, source=str(src), rows=len(df), extra={"brut": avant})
        logger.info("OSM silver %s : %d POI (sur %d bruts) → %s", dep, len(df), avant, out)
        produced.append(out)
    return produced
