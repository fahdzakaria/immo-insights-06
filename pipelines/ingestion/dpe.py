"""Ingestion DPE logements existants (ADEME, data.ademe.fr) → bronze.

Source : API data-fair, dataset `dpe03existant` (~15 M de DPE depuis juillet
2021). On filtre côté API par département et on ne sélectionne que les
colonnes utiles (le dataset complet compte 200+ colonnes) : ~290 k lignes
pour le 06, paginées par curseur `after` (le lien `next` de chaque réponse).

Sortie : data/bronze/dpe/departement={dep}/dpe.parquet
"""

import logging
from pathlib import Path

import pandas as pd

from pipelines.common import already_ingested, atomic_write_parquet, http_get, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.dpe")

API_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
PAGE_SIZE = 10_000

# L'ADEME ajoute des DPE en continu : rafraîchissement hebdomadaire
FRAICHEUR_JOURS = 7
# Part minimale du total annoncé par l'API pour accepter le téléchargement
TOLERANCE_COMPLETUDE = 0.99

# Colonnes vérifiées sur le schéma réel du dataset (juillet 2026)
SELECT_COLS = [
    "numero_dpe",
    "date_etablissement_dpe",
    "date_reception_dpe",
    "etiquette_dpe",
    "etiquette_ges",
    "type_batiment",
    "periode_construction",
    "surface_habitable_logement",
    "conso_5_usages_par_m2_ep",
    "emission_ges_5_usages_par_m2",
    "type_energie_principale_chauffage",
    "type_energie_principale_ecs",
    "adresse_ban",
    "code_postal_ban",
    "code_insee_ban",
    "code_departement_ban",
    "nom_commune_ban",
    "_geopoint",
]


def rows_from_response(data: dict) -> list[dict]:
    """Aplati une page de résultats data-fair ; extrait lat/lon du _geopoint."""
    rows = []
    for r in data.get("results", []):
        row = {c: r.get(c) for c in SELECT_COLS if c != "_geopoint"}
        geopoint = r.get("_geopoint") or ""
        lat, _, lon = geopoint.partition(",")
        row["latitude"] = float(lat) if lat else None
        row["longitude"] = float(lon) if lon else None
        rows.append(row)
    return rows


def verifier_complet(nb_lignes: int, total_annonce: int | None, dep: str) -> None:
    """Refuse un téléchargement tronqué (pagination interrompue sans erreur).

    Sans ce contrôle un parquet partiel serait écrit puis considéré « frais »
    pendant FRAICHEUR_JOURS. Tolérance 1 % : l'API reçoit des DPE en continu.
    """
    if total_annonce and nb_lignes < TOLERANCE_COMPLETUDE * total_annonce:
        raise ValueError(
            f"DPE {dep} incomplet : {nb_lignes} lignes reçues sur {total_annonce} annoncées"
        )


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    produced: list[Path] = []
    for dep in departements:
        source = f"{API_URL}?departement={dep}"
        out = BRONZE_DIR / "dpe" / f"departement={dep}" / "dpe.parquet"
        if already_ingested(out, source=source, force=force, max_age_jours=FRAICHEUR_JOURS):
            produced.append(out)
            continue

        params = {
            "size": PAGE_SIZE,
            "qs": f'code_departement_ban:"{dep}"',
            "select": ",".join(c for c in SELECT_COLS if c != "_geopoint") + ",_geopoint",
        }
        all_rows: list[dict] = []
        total_annonce: int | None = None  # présent seulement sur la 1re page
        url, page = API_URL, 0
        while url:
            data = http_get(url, params=params).json()
            params = None  # le lien `next` embarque déjà tous les paramètres
            all_rows.extend(rows_from_response(data))
            if total_annonce is None:
                total_annonce = data.get("total")
            page += 1
            logger.info("DPE %s : page %d, %d lignes cumulées (total annoncé %s)",
                        dep, page, len(all_rows), data.get("total"))
            url = data.get("next")

        verifier_complet(len(all_rows), total_annonce, dep)
        df = pd.DataFrame(all_rows)
        if not df.empty:
            # Dates en datetime pour le parquet (les codes restent en texte)
            for col in ("date_etablissement_dpe", "date_reception_dpe"):
                df[col] = pd.to_datetime(df[col], errors="coerce")
        atomic_write_parquet(df, out)
        write_manifest(out, source=source, rows=len(df), extra={"departement": dep})
        logger.info("DPE %s : %d diagnostics → %s", dep, len(df), out)
        produced.append(out)
    return produced
