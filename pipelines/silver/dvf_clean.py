"""Silver DVF : des mutations brutes aux « ventes propres » analysables.

RÈGLES DE NETTOYAGE (toutes documentées dans docs/silver.md) :
 R1. nature_mutation ∈ {Vente, Vente en l'état futur d'achèvement}
 R2. type_local ∈ {Appartement, Maison} (dépendances et locaux pro exclus)
 R3. dédoublonnage : DVF répète une ligne par disposition/lot
 R4. « ventes simples » : on ne garde que les mutations portant sur UN SEUL
     logement — quand une mutation vend 3 appartements, la valeur foncière
     est globale et le prix/m² serait faux
 R5. valeur foncière renseignée, entre 10 000 € et 20 M€
 R6. surface bâtie renseignée, entre 8 m² et 1 000 m²
 R7. prix/m² entre 500 €/m² et 50 000 €/m² (bornes larges : le 06 monte haut)
 R8. code commune renseigné
 R9. géocodage BAN des ventes retenues sans coordonnées (cache local)

Sortie : data/silver/dvf/departement={dep}/ventes.parquet
"""

import logging
from pathlib import Path

import duckdb
import pandas as pd

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import BRONZE_DIR, SILVER_DIR
from pipelines.silver.geocodage import geocoder_ban

logger = logging.getLogger("silver.dvf")

NATURES_RETENUES = ("Vente", "Vente en l'état futur d'achèvement")
TYPES_RETENUS = ("Appartement", "Maison")
PRIX_MIN, PRIX_MAX = 10_000, 20_000_000
SURFACE_MIN, SURFACE_MAX = 8, 1_000
PRIX_M2_MIN, PRIX_M2_MAX = 500, 50_000


def nettoyer(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Applique les règles R1→R8 ; retourne (ventes propres, stats par règle)."""
    stats = {"brut": len(df)}

    df = df[df["nature_mutation"].isin(NATURES_RETENUES)]
    stats["r1_nature_vente"] = len(df)

    logements = df[df["type_local"].isin(TYPES_RETENUS)].copy()
    stats["r2_logements"] = len(logements)

    # R3 — une ligne par (mutation, parcelle, local) : DVF duplique par lot
    logements = logements.drop_duplicates(
        subset=["id_mutation", "id_parcelle", "type_local", "surface_reelle_bati", "valeur_fonciere"]
    )
    stats["r3_dedoublonne"] = len(logements)

    # R4 — mutations mono-logement uniquement
    nb_logements = logements.groupby("id_mutation")["id_parcelle"].transform("size")
    ventes = logements[nb_logements == 1].copy()
    stats["r4_vente_simple"] = len(ventes)

    ventes["valeur_fonciere"] = pd.to_numeric(ventes["valeur_fonciere"], errors="coerce")
    ventes["surface_reelle_bati"] = pd.to_numeric(ventes["surface_reelle_bati"], errors="coerce")
    ventes = ventes[ventes["valeur_fonciere"].between(PRIX_MIN, PRIX_MAX)]
    stats["r5_prix_plausible"] = len(ventes)

    ventes = ventes[ventes["surface_reelle_bati"].between(SURFACE_MIN, SURFACE_MAX)]
    stats["r6_surface_plausible"] = len(ventes)

    ventes["prix_m2"] = ventes["valeur_fonciere"] / ventes["surface_reelle_bati"]
    ventes = ventes[ventes["prix_m2"].between(PRIX_M2_MIN, PRIX_M2_MAX)]
    stats["r7_prix_m2_plausible"] = len(ventes)

    ventes = ventes[ventes["code_commune"].notna()]
    stats["r8_commune_connue"] = len(ventes)
    return ventes, stats


def normaliser(ventes: pd.DataFrame) -> pd.DataFrame:
    """Schéma silver : colonnes utiles, types propres, dérivées temporelles."""
    out = pd.DataFrame({
        "id_mutation": ventes["id_mutation"],
        "date_mutation": pd.to_datetime(ventes["date_mutation"]),
        "nature_mutation": ventes["nature_mutation"],
        "type_bien": ventes["type_local"].str.lower(),  # appartement | maison
        "valeur_fonciere": ventes["valeur_fonciere"],
        "surface_bati": ventes["surface_reelle_bati"],
        "prix_m2": ventes["prix_m2"].round(2),
        "nb_pieces": pd.to_numeric(ventes["nombre_pieces_principales"], errors="coerce"),
        "surface_terrain": pd.to_numeric(ventes["surface_terrain"], errors="coerce"),
        "adresse_numero": ventes["adresse_numero"],
        "adresse_nom_voie": ventes["adresse_nom_voie"],
        "code_postal": ventes["code_postal"],
        "code_commune": ventes["code_commune"],
        "nom_commune": ventes["nom_commune"],
        "code_departement": ventes["code_departement"],
        "id_parcelle": ventes["id_parcelle"],
        "longitude": pd.to_numeric(ventes["longitude"], errors="coerce"),
        "latitude": pd.to_numeric(ventes["latitude"], errors="coerce"),
    })
    out["annee"] = out["date_mutation"].dt.year
    out["trimestre"] = out["date_mutation"].dt.to_period("Q").astype(str)  # ex: 2024Q3
    out["geocode_source"] = out["latitude"].notna().map({True: "dvf", False: None})
    return out


def build(departements: list[str]) -> list[Path]:
    produced = []
    for dep in departements:
        glob = str(BRONZE_DIR / "dvf" / f"departement={dep}" / "annee=*" / "dvf.parquet")
        df = duckdb.sql(f"SELECT * FROM read_parquet('{glob}')").df()

        ventes, stats = nettoyer(df)
        ventes = normaliser(ventes)
        logger.info("DVF %s — entonnoir de nettoyage : %s", dep, stats)

        # R9 — géocodage BAN des ventes sans coordonnées
        ventes = geocoder_ban(ventes)

        out = SILVER_DIR / "dvf" / f"departement={dep}" / "ventes.parquet"
        atomic_write_parquet(ventes, out)
        write_manifest(out, source=glob, rows=len(ventes), extra={"regles": stats})
        logger.info("DVF silver %s : %d ventes propres → %s", dep, len(ventes), out)
        produced.append(out)
    return produced
