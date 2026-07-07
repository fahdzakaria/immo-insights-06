"""Ingestion INSEE « Base comparateur de territoires » → bronze.

Un seul fichier national par commune avec population, médiane du niveau de
vie, taux de pauvreté, emploi, etc. (millésime mis à jour par l'INSEE).
Source : https://www.insee.fr/fr/statistiques/2521169

Le zip contient le CSV de données + un CSV de métadonnées (dictionnaire des
variables) ; on garde les deux en bronze.

Sortie : data/bronze/insee/base_comparateur.parquet (+ _meta.parquet)
"""

import io
import logging
import zipfile
from pathlib import Path

from pipelines.common import already_ingested, atomic_write_parquet, download_bytes, read_csv_flexible, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.insee")

# Millésime INSEE annuel : re-téléchargement mensuel suffit
FRAICHEUR_JOURS = 30

INSEE_COMPARATEUR_URL = "https://www.insee.fr/fr/statistiques/fichier/2521169/base_cc_comparateur_csv.zip"


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    # Fichier national : le paramètre departements ne sert pas ici (filtrage en silver)
    out = BRONZE_DIR / "insee" / "base_comparateur.parquet"
    out_meta = BRONZE_DIR / "insee" / "base_comparateur_meta.parquet"
    if already_ingested(out, source=INSEE_COMPARATEUR_URL, force=force, max_age_jours=FRAICHEUR_JOURS):
        return [out, out_meta]

    payload = download_bytes(INSEE_COMPARATEUR_URL)
    produced: list[Path] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        # Le CSV de métadonnées contient "meta" dans son nom, l'autre est la donnée
        data_name = next(n for n in csv_names if "meta" not in n.lower())
        meta_names = [n for n in csv_names if "meta" in n.lower()]

        # Codes commune en texte pour préserver les zéros de tête (ex : 06004)
        df = read_csv_flexible(zf.read(data_name), dtype="string")
        atomic_write_parquet(df, out)
        write_manifest(out, source=INSEE_COMPARATEUR_URL, rows=len(df), extra={"fichier": data_name})
        logger.info("INSEE comparateur : %d communes, %d colonnes → %s", len(df), df.shape[1], out)
        produced.append(out)

        if meta_names:
            df_meta = read_csv_flexible(zf.read(meta_names[0]), dtype="string")
            atomic_write_parquet(df_meta, out_meta)
            write_manifest(out_meta, source=INSEE_COMPARATEUR_URL, rows=len(df_meta), extra={"fichier": meta_names[0]})
            produced.append(out_meta)
    return produced
