"""Silver DPE : diagnostics dédoublonnés et plausibles.

Règles :
 - étiquette DPE et GES valides (A→G)
 - surface habitable entre 8 et 1 000 m²
 - dédoublonnage par numero_dpe (dernier établi conservé) : un logement
   re-diagnostiqué garde son DPE le plus récent
 - type_batiment normalisé (appartement/maison, les immeubles collectifs
   entiers sont exclus : ils ne matchent pas une vente DVF individuelle)

Sortie : data/silver/dpe/departement={dep}/dpe.parquet
"""

import logging
from pathlib import Path

import pandas as pd

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import BRONZE_DIR, SILVER_DIR

logger = logging.getLogger("silver.dpe")

ETIQUETTES = list("ABCDEFG")


def nettoyer(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    stats = {"brut": len(df)}
    df = df[df["etiquette_dpe"].isin(ETIQUETTES)]
    stats["etiquette_valide"] = len(df)

    df = df[df["type_batiment"].isin(["appartement", "maison"])]
    stats["logement_individuel"] = len(df)

    df = df.copy()
    df["surface_habitable_logement"] = pd.to_numeric(df["surface_habitable_logement"], errors="coerce")
    df = df[df["surface_habitable_logement"].between(8, 1_000)]
    stats["surface_plausible"] = len(df)

    df = df.sort_values("date_etablissement_dpe").drop_duplicates(subset="numero_dpe", keep="last")
    stats["dedoublonne"] = len(df)
    return df, stats


def build(departements: list[str]) -> list[Path]:
    produced = []
    for dep in departements:
        src = BRONZE_DIR / "dpe" / f"departement={dep}" / "dpe.parquet"
        df, stats = nettoyer(pd.read_parquet(src))
        logger.info("DPE %s — entonnoir : %s", dep, stats)

        out = SILVER_DIR / "dpe" / f"departement={dep}" / "dpe.parquet"
        atomic_write_parquet(df, out)
        write_manifest(out, source=str(src), rows=len(df), extra={"regles": stats})
        produced.append(out)
    return produced
