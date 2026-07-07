"""Géocodage BAN (api-adresse.data.gouv.fr) des ventes sans coordonnées.

~1 à 3 % des lignes DVF n'ont pas de lat/lon. On les géocode par lot via
l'endpoint CSV de la BAN (bien plus rapide que du ligne à ligne), avec un
CACHE Parquet persistant : une adresse déjà résolue n'est jamais renvoyée
à l'API, même après un --force ou un nouveau département.

Seuls les résultats avec un score BAN ≥ 0.5 sont retenus.
"""

import io
import logging
from pathlib import Path

import pandas as pd

from pipelines.common import _session
from pipelines.config import SILVER_DIR

logger = logging.getLogger("silver.geocodage")

BAN_CSV_URL = "https://api-adresse.data.gouv.fr/search/csv/"
SCORE_MIN = 0.5
BATCH_SIZE = 3_000
CACHE_PATH = SILVER_DIR / "geocodage_cache.parquet"


def adresse_texte(df: pd.DataFrame) -> pd.Series:
    """Concatène numéro + voie (le code postal part dans une colonne dédiée BAN)."""
    numero = df["adresse_numero"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    voie = df["adresse_nom_voie"].fillna("").astype(str)
    return (numero + " " + voie).str.strip()


def _charger_cache() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_parquet(CACHE_PATH)
    return pd.DataFrame(columns=["adresse", "code_postal", "ban_lat", "ban_lon", "ban_score"])


def _appeler_ban(batch: pd.DataFrame) -> pd.DataFrame:
    """Envoie un lot d'adresses à l'endpoint CSV de la BAN."""
    csv_bytes = batch.to_csv(index=False).encode("utf-8")
    resp = _session.post(
        BAN_CSV_URL,
        files={"data": ("adresses.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={
            "columns": "adresse",
            "postcode": "code_postal",
            "result_columns": ["latitude", "longitude", "result_score"],
        },
        timeout=300,
    )
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), dtype={"code_postal": "string"})


def geocoder_ban(ventes: pd.DataFrame) -> pd.DataFrame:
    """Complète latitude/longitude des ventes qui n'en ont pas (via cache + BAN)."""
    manquantes = ventes["latitude"].isna() & ventes["adresse_nom_voie"].notna()
    if not manquantes.any():
        logger.info("Géocodage : aucune vente sans coordonnées")
        return ventes

    a_geocoder = ventes.loc[manquantes, ["adresse_numero", "adresse_nom_voie", "code_postal"]].copy()
    a_geocoder["adresse"] = adresse_texte(a_geocoder)
    a_geocoder = a_geocoder[a_geocoder["adresse"].str.len() > 3]
    demandes = a_geocoder[["adresse", "code_postal"]].drop_duplicates()

    cache = _charger_cache()
    connues = demandes.merge(cache, on=["adresse", "code_postal"], how="inner")
    nouvelles = demandes.merge(cache[["adresse", "code_postal"]], on=["adresse", "code_postal"],
                               how="left", indicator=True)
    nouvelles = nouvelles[nouvelles["_merge"] == "left_only"].drop(columns="_merge")
    logger.info("Géocodage : %d adresses uniques (%d en cache, %d à résoudre)",
                len(demandes), len(connues), len(nouvelles))

    resultats = []
    for start in range(0, len(nouvelles), BATCH_SIZE):
        batch = nouvelles.iloc[start:start + BATCH_SIZE]
        rep = _appeler_ban(batch)
        rep = rep.rename(columns={"latitude": "ban_lat", "longitude": "ban_lon",
                                  "result_score": "ban_score"})
        resultats.append(rep[["adresse", "code_postal", "ban_lat", "ban_lon", "ban_score"]])
        logger.info("Géocodage : lot %d-%d envoyé à la BAN", start, start + len(batch))

    if resultats:
        cache = pd.concat([cache, *resultats], ignore_index=True)
        cache = cache.drop_duplicates(subset=["adresse", "code_postal"], keep="last")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cache.to_parquet(CACHE_PATH, index=False)

    # Application aux ventes : uniquement les scores fiables.
    # NB : merge en préservant l'index d'origine pour réaligner sur `ventes`.
    fiable = cache[pd.to_numeric(cache["ban_score"], errors="coerce") >= SCORE_MIN]
    resolu = (
        a_geocoder.reset_index()
        .merge(fiable, on=["adresse", "code_postal"], how="left")
        .set_index("index")
    )
    ventes = ventes.copy()
    ventes.loc[resolu.index, "latitude"] = ventes.loc[resolu.index, "latitude"].fillna(resolu["ban_lat"])
    ventes.loc[resolu.index, "longitude"] = ventes.loc[resolu.index, "longitude"].fillna(resolu["ban_lon"])
    geocodees = ventes.loc[resolu.index, "latitude"].notna()
    ventes.loc[geocodees[geocodees].index, "geocode_source"] = "ban"
    logger.info("Géocodage : %d/%d ventes complétées (score ≥ %s)",
                int(geocodees.sum()), int(manquantes.sum()), SCORE_MIN)
    return ventes
