"""Ingestion « Carte des loyers » (Ministère de la Transition écologique) → bronze.

Indicateurs de loyers d'annonce par commune (millésime 2025). Quatre fichiers
nationaux : appartements (tous), 1-2 pièces, 3 pièces et plus, maisons.
Les IDs de ressources data.gouv sont stables (liens permanents /datasets/r/{id}).

Sortie : data/bronze/loyers/{segment}.parquet
"""

import logging
from pathlib import Path

from pipelines.common import already_ingested, atomic_write_parquet, download_bytes, read_csv_flexible, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.loyers")

# Dataset "Carte des loyers 2025" : https://www.data.gouv.fr/fr/datasets/693aa2feed1bf4da603faa49/
RESOURCES = {
    "appartement": "55b34088-0964-415f-9df7-d87dd98a09be",
    "appartement_1_2p": "14a1fe11-b2d1-49b3-9f6b-83d12df9482c",
    "appartement_3p_plus": "5e3b28a4-cf56-43a3-ae79-43cceeb27f8c",
    "maison": "129f764d-b613-44e4-952c-5ff50a8c9b73",
}


# Carte des loyers : millésime annuel, re-téléchargement mensuel
FRAICHEUR_JOURS = 30


def resource_url(resource_id: str) -> str:
    return f"https://www.data.gouv.fr/fr/datasets/r/{resource_id}"


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    # Fichiers nationaux : filtrage par département en silver
    produced: list[Path] = []
    for segment, rid in RESOURCES.items():
        url = resource_url(rid)
        out = BRONZE_DIR / "loyers" / f"{segment}.parquet"
        if already_ingested(out, source=url, force=force, max_age_jours=FRAICHEUR_JOURS):
            produced.append(out)
            continue
        payload = download_bytes(url)
        # Tout en texte : les décimales à virgule française seront parsées en silver
        df = read_csv_flexible(payload, dtype="string")
        atomic_write_parquet(df, out)
        write_manifest(out, source=url, rows=len(df), extra={"segment": segment})
        logger.info("Loyers %s : %d communes → %s", segment, len(df), out)
        produced.append(out)
    return produced
