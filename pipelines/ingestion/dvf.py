"""Ingestion DVF géolocalisé (Etalab / data.gouv.fr) → bronze.

Source : https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dep}.csv.gz
Un fichier par année et par département. La publication est une fenêtre
glissante d'environ 5 ans : une année absente (404) est ignorée avec un warning.

Sortie : data/bronze/dvf/departement={dep}/annee={annee}/dvf.parquet
"""

import gzip
import io
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from pipelines.common import already_ingested, atomic_write_parquet, download_bytes, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.dvf")

DVF_URL_TEMPLATE = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dep}.csv.gz"

# Etalab republie DVF ~2×/an sous les mêmes URLs : re-téléchargement bimensuel
FRAICHEUR_JOURS = 15

# Colonnes à lire comme texte : codes à zéros significatifs (06000 ≠ 6000)
_STR_COLS = [
    "id_mutation", "numero_disposition", "adresse_numero", "adresse_suffixe",
    "adresse_nom_voie", "adresse_code_voie", "code_postal", "code_commune",
    "nom_commune", "code_departement", "ancien_code_commune", "ancien_nom_commune",
    "id_parcelle", "ancien_id_parcelle", "numero_volume",
    "lot1_numero", "lot2_numero", "lot3_numero", "lot4_numero", "lot5_numero",
    "type_local", "code_type_local", "nature_mutation", "nature_culture",
    "code_nature_culture", "nature_culture_speciale", "code_nature_culture_speciale",
]


def annees() -> list[int]:
    """Années à ingérer : de DVF_ANNEE_DEBUT (2021) à l'année en cours.

    L'année en cours est incluse d'office : dès qu'Etalab la publie elle est
    ingérée sans toucher au code (avant publication : 404, ignoré plus bas).
    DVF_ANNEES="2021,2022,..." force une liste précise.
    """
    raw = os.environ.get("DVF_ANNEES")
    if raw:
        return [int(a.strip()) for a in raw.split(",") if a.strip()]
    debut = int(os.environ.get("DVF_ANNEE_DEBUT") or "2021")
    return list(range(debut, date.today().year + 1))


def dvf_url(dep: str, annee: int) -> str:
    return DVF_URL_TEMPLATE.format(annee=annee, dep=dep)


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    produced: list[Path] = []
    for dep in departements:
        for annee in annees():
            url = dvf_url(dep, annee)
            out = BRONZE_DIR / "dvf" / f"departement={dep}" / f"annee={annee}" / "dvf.parquet"
            if already_ingested(out, source=url, force=force, max_age_jours=FRAICHEUR_JOURS):
                produced.append(out)
                continue
            try:
                payload = download_bytes(url)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    logger.warning("DVF %s/%s indisponible (404) — fenêtre glissante, on ignore", dep, annee)
                    continue
                raise
            csv_bytes = gzip.decompress(payload)
            df = pd.read_csv(
                io.BytesIO(csv_bytes),
                dtype={c: "string" for c in _STR_COLS},
                low_memory=False,
            )
            atomic_write_parquet(df, out)
            write_manifest(out, source=url, rows=len(df), extra={"departement": dep, "annee": annee})
            logger.info("DVF %s/%s : %d transactions → %s", dep, annee, len(df), out)
            produced.append(out)
    return produced
