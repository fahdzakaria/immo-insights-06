"""Ingestion INSEE « Base comparateur de territoires » → bronze.

Un seul fichier national avec population, médiane du niveau de vie, taux de
pauvreté, logements, etc. (millésime mis à jour par l'INSEE).
Source : https://www.insee.fr/fr/statistiques/2521169

Depuis 2026 l'INSEE publie ce fichier au FORMAT LONG (catalogue Melodi) :
une ligne par (territoire, année, mesure) au lieu d'une colonne par
indicateur. Le bronze garde le fichier tel quel ; le passage en une ligne par
commune se fait en silver (referentiels.pivoter_insee). Un garde-fou vérifie
les colonnes attendues : si l'INSEE change encore de format, la tâche échoue
ici avec un message clair plutôt que plus loin avec une erreur obscure.

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

INSEE_COMPARATEUR_URL = "https://www.insee.fr/fr/statistiques/fichier/2521169/comparateur_csv.zip"

# Colonnes du format long dont dépend le silver
COLONNES_ATTENDUES = {"GEO_OBJECT", "GEO", "TIME_PERIOD", "TAB_MEASURE", "OBS_VALUE"}


def verifier_schema(colonnes) -> None:
    """Échoue explicitement si le fichier INSEE n'a plus le format attendu."""
    manquantes = COLONNES_ATTENDUES - set(colonnes)
    if manquantes:
        raise ValueError(
            f"Format INSEE inattendu : colonnes manquantes {sorted(manquantes)} "
            f"(reçues : {sorted(colonnes)[:15]}). Vérifier {INSEE_COMPARATEUR_URL}"
        )


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
        verifier_schema(df.columns)
        atomic_write_parquet(df, out)
        write_manifest(out, source=INSEE_COMPARATEUR_URL, rows=len(df), extra={"fichier": data_name})
        logger.info("INSEE comparateur : %d lignes, %d colonnes → %s", len(df), df.shape[1], out)
        produced.append(out)

        if meta_names:
            df_meta = read_csv_flexible(zf.read(meta_names[0]), dtype="string")
            atomic_write_parquet(df_meta, out_meta)
            write_manifest(out_meta, source=INSEE_COMPARATEUR_URL, rows=len(df_meta), extra={"fichier": meta_names[0]})
            produced.append(out_meta)
    return produced
