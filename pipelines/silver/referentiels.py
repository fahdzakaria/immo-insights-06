"""Silver référentiels communaux : INSEE (socio-éco) + carte des loyers.

- INSEE : sélection/renommage des indicateurs utiles du comparateur de
  territoires (millésimes 2022/2023), cast numérique.
- Loyers : les 4 segments (appart tous / 1-2 p / 3 p+ / maison) pivotés en
  une ligne par commune, décimales à virgule française parsées.

Sorties : data/silver/insee/communes.parquet
          data/silver/loyers/communes.parquet
"""

import logging
from pathlib import Path

import pandas as pd

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import BRONZE_DIR, SILVER_DIR

logger = logging.getLogger("silver.referentiels")

# Mapping colonnes INSEE (base comparateur, millésime 2025) → noms lisibles
INSEE_COLS = {
    "CODGEO": "code_commune",
    "P22_POP": "population",
    "P16_POP": "population_2016",
    "SUPERF": "superficie_km2",
    "P22_MEN": "menages",
    "P22_LOG": "logements",
    "P22_RP": "residences_principales",
    "P22_RSECOCC": "residences_secondaires",
    "P22_LOGVAC": "logements_vacants",
    "P22_RP_PROP": "rp_proprietaires",
    "MED_SL23": "niveau_vie_median",
    "PR_MD60_23": "taux_pauvrete",
    "P22_EMPLT": "emplois",
    "P22_ACT1564": "actifs_15_64",
    "P22_CHOM1564": "chomeurs_15_64",
    "ETTOT24": "etablissements",
}


def _num(s: pd.Series) -> pd.Series:
    """Cast numérique tolérant : décimales à virgule, espaces, valeurs manquantes."""
    return pd.to_numeric(
        s.astype("string").str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )


def build_insee() -> Path:
    src = BRONZE_DIR / "insee" / "base_comparateur.parquet"
    df = pd.read_parquet(src, columns=list(INSEE_COLS)).rename(columns=INSEE_COLS)
    for col in df.columns:
        if col != "code_commune":
            df[col] = _num(df[col])

    # Dérivées utiles aux marts
    df["taux_logements_vacants"] = (df["logements_vacants"] / df["logements"] * 100).round(2)
    df["taux_residences_secondaires"] = (df["residences_secondaires"] / df["logements"] * 100).round(2)
    df["taux_chomage_15_64"] = (df["chomeurs_15_64"] / df["actifs_15_64"] * 100).round(2)
    df["evolution_population_pct"] = (
        (df["population"] - df["population_2016"]) / df["population_2016"] * 100
    ).round(2)

    out = SILVER_DIR / "insee" / "communes.parquet"
    atomic_write_parquet(df, out)
    write_manifest(out, source=str(src), rows=len(df))
    logger.info("INSEE silver : %d communes, %d colonnes → %s", len(df), df.shape[1], out)
    return out


LOYERS_SEGMENTS = {
    "appartement": "loyer_m2_appartement",
    "appartement_1_2p": "loyer_m2_appart_1_2p",
    "appartement_3p_plus": "loyer_m2_appart_3p_plus",
    "maison": "loyer_m2_maison",
}


def build_loyers() -> Path:
    merged: pd.DataFrame | None = None
    for segment, col_cible in LOYERS_SEGMENTS.items():
        src = BRONZE_DIR / "loyers" / f"{segment}.parquet"
        df = pd.read_parquet(src)
        part = pd.DataFrame({
            "code_commune": df["INSEE_C"],
            "nom_commune": df["LIBGEO"],
            col_cible: _num(df["loypredm2"]).round(2),
            # La prédiction est-elle au niveau commune ou maille plus large ?
            f"{col_cible}_fiabilite": df["TYPPRED"],
        })
        merged = part if merged is None else merged.merge(
            part.drop(columns="nom_commune"), on="code_commune", how="outer")

    out = SILVER_DIR / "loyers" / "communes.parquet"
    atomic_write_parquet(merged, out)
    write_manifest(out, source=str(BRONZE_DIR / "loyers"), rows=len(merged))
    logger.info("Loyers silver : %d communes → %s", len(merged), out)
    return out


def build(departements: list[str]) -> list[Path]:
    # Référentiels nationaux : le filtrage par département se fait à la jointure
    return [build_insee(), build_loyers()]
