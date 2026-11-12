"""Silver référentiels communaux : INSEE (socio-éco) + carte des loyers.

- INSEE : le comparateur de territoires arrive au format long (une ligne par
  commune × année × mesure) ; on le pivote en une ligne par commune avec le
  dernier millésime de chaque mesure.
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
from pipelines.ingestion.insee import COLONNES_ATTENDUES

logger = logging.getLogger("silver.referentiels")

# Mesures INSEE (format long Melodi, colonne TAB_MEASURE) → noms lisibles
INSEE_MESURES = {
    "POP": "population",
    "SUP": "superficie_km2",
    "DWELLINGS": "logements",
    "DWELLINGS_OCS_DW_MAIN": "residences_principales",
    "DWELLINGS_OCS_DW_SEC_DW_OCC": "residences_secondaires",
    "DWELLINGS_OCS_DW_VAC": "logements_vacants",
    "DWELLINGS_OCS_DW_MAIN_TSH_100": "rp_proprietaires",
    "MED_SL": "niveau_vie_median",
    "PR_MD60": "taux_pauvrete",
    "NBEMP_EMPFORM_2": "emplois_salaries",
    "POP_AGE_Y15T64": "population_15_64",
    "UNIT_LOC": "etablissements",
}
# Communes + arrondissements municipaux (Paris/Lyon/Marseille : DVF y code
# les ventes à l'arrondissement)
INSEE_NIVEAUX = ("COM", "ARM")
# Écart minimal (années) entre les deux populations comparées
ECART_MIN_POP_ANS = 5


def _num(s: pd.Series) -> pd.Series:
    """Cast numérique tolérant : décimales à virgule, espaces, valeurs manquantes."""
    return pd.to_numeric(
        s.astype("string").str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )


def pivoter_insee(df_long: pd.DataFrame) -> pd.DataFrame:
    """Format long INSEE → une ligne par commune.

    Pour chaque mesure on garde le millésime le plus récent. La population
    est aussi prise au recensement précédent (`population_ref`) pour calculer
    son évolution. Mesure absente du fichier → erreur explicite.
    """
    df = df_long[df_long["GEO_OBJECT"].isin(INSEE_NIVEAUX)
                 & df_long["TAB_MEASURE"].isin(INSEE_MESURES)].copy()
    absentes = set(INSEE_MESURES) - set(df["TAB_MEASURE"].unique())
    if absentes:
        raise ValueError(f"Mesures INSEE absentes du fichier : {sorted(absentes)}")

    df["annee"] = pd.to_numeric(df["TIME_PERIOD"], errors="coerce")
    df["valeur"] = _num(df["OBS_VALUE"]).astype("float64")  # NaN numpy, pas pd.NA
    df = df.dropna(subset=["annee"])

    # Un même (territoire, mesure, année) en double = le fichier a changé
    # (nouvelle source, code partagé COM/ARM…) : on refuse plutôt que d'écraser.
    doublons = df.duplicated(subset=["GEO", "TAB_MEASURE", "annee"]).sum()
    if doublons:
        raise ValueError(f"INSEE : {doublons} doublons (territoire, mesure, année) — format à revoir")

    # Dernier millésime RENSEIGNÉ par commune × mesure : une commune dont une
    # valeur manque au dernier millésime garde la précédente au lieu de NaN.
    derniers = (
        df.dropna(subset=["valeur"]).sort_values("annee")
        .groupby(["GEO", "TAB_MEASURE"], sort=False).tail(1)
    )
    out = (
        derniers.pivot(index="GEO", columns="TAB_MEASURE", values="valeur")
        .rename(columns=INSEE_MESURES)
        .reindex(index=sorted(df["GEO"].unique()), columns=list(INSEE_MESURES.values()))
    )

    # Population de référence : recensement le plus récent situé au moins
    # ECART_MIN_POP_ANS avant le dernier (ex : 2017 pour 2023). L'écart minimal
    # évite de comparer à l'année N-1 si l'INSEE publie un jour une série annuelle.
    pop = df[df["TAB_MEASURE"] == "POP"]
    annee_pop = int(pop["annee"].max())
    candidates = [a for a in pop["annee"].unique() if a <= annee_pop - ECART_MIN_POP_ANS]
    out["annee_population"] = annee_pop
    if candidates:
        annee_ref = int(max(candidates))
        ref = pop[pop["annee"] == annee_ref].set_index("GEO")["valeur"]
        out["population_ref"] = ref.reindex(out.index)
        out["annee_population_ref"] = annee_ref
    else:
        out["population_ref"] = float("nan")
        out["annee_population_ref"] = pd.NA

    out = out.rename_axis("code_commune").reset_index()
    out.columns.name = None

    # Dérivées utiles aux marts
    out["menages"] = out["residences_principales"]  # un ménage = une résidence principale
    out["taux_logements_vacants"] = (out["logements_vacants"] / out["logements"] * 100).round(2)
    out["taux_residences_secondaires"] = (out["residences_secondaires"] / out["logements"] * 100).round(2)
    out["evolution_population_pct"] = (
        (out["population"] - out["population_ref"]) / out["population_ref"] * 100
    ).round(2)
    return out


def build_insee() -> Path:
    src = BRONZE_DIR / "insee" / "base_comparateur.parquet"
    brut = pd.read_parquet(src)
    colonnes = COLONNES_ATTENDUES
    if not colonnes <= set(brut.columns):
        raise ValueError(
            f"{src} n'est pas au format long INSEE attendu (colonnes : {list(brut.columns)[:10]}). "
            "Relancer l'ingestion INSEE."
        )
    df = pivoter_insee(brut[sorted(colonnes)])

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
            # Intervalle de prédiction publié avec la carte + nombre d'annonces
            # observées dans la commune : sert à borner le rendement
            f"{col_cible}_bas": _num(df["lwr.IPm2"]).round(2),
            f"{col_cible}_haut": _num(df["upr.IPm2"]).round(2),
            f"{col_cible}_nb_annonces": _num(df["nbobs_com"]),
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
