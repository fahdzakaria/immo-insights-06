"""Endpoints communes : liste filtrable (carte + comparateur) et fiche détail."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.cache import ttl_cache

router = APIRouter(prefix="/api/v1/communes", tags=["communes"])

# Tri par LISTE BLANCHE : jamais de colonne injectée par l'utilisateur
TRIS = {
    "prix_m2": "prix_m2_median",
    "ventes": "nb_ventes_total",
    "evolution": "evolution_1an_pct",
    "population": "population",
    "nom": "nom_commune",
}


@ttl_cache
def _liste(departement, type_bien, prix_m2_min, prix_m2_max, population_min,
           recherche, tri, ordre, limit, offset):
    filtres, params = ["code_departement = ?"], [departement]
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    if prix_m2_min is not None:
        filtres.append("prix_m2_median >= ?")
        params.append(prix_m2_min)
    if prix_m2_max is not None:
        filtres.append("prix_m2_median <= ?")
        params.append(prix_m2_max)
    if population_min is not None:
        filtres.append("population >= ?")
        params.append(population_min)
    if recherche:
        filtres.append("nom_commune ILIKE '%' || ? || '%'")
        params.append(recherche)

    where = " AND ".join(filtres)
    total = db.query_one(f"SELECT count(*) AS n FROM mart_prix_m2_par_commune WHERE {where}", params)["n"]
    lignes = db.query(
        f"""SELECT * FROM mart_prix_m2_par_commune
            WHERE {where}
            ORDER BY {TRIS[tri]} {"DESC" if ordre == "desc" else "ASC"} NULLS LAST
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    return {"total": total, "limit": limit, "offset": offset, "resultats": lignes}


@router.get("", summary="Communes avec prix au m², filtrables (alimente carte et tableau)")
def liste_communes(
    departement: str = Query("06", pattern=r"^(\d{2,3}|2A|2B)$"),
    type_bien: Literal["appartement", "maison"] | None = None,
    prix_m2_min: float | None = Query(None, ge=0),
    prix_m2_max: float | None = Query(None, ge=0),
    population_min: int | None = Query(None, ge=0),
    recherche: str | None = Query(None, max_length=60, description="Recherche sur le nom de commune"),
    tri: Literal["prix_m2", "ventes", "evolution", "population", "nom"] = "ventes",
    ordre: Literal["asc", "desc"] = "desc",
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return _liste(departement, type_bien, prix_m2_min, prix_m2_max, population_min,
                  recherche, tri, ordre, limit, offset)


@router.get("/{code_commune}", summary="Fiche complète d'une commune (prix, rendement, score)")
def detail_commune(code_commune: str):
    prix = db.query(
        "SELECT * FROM mart_prix_m2_par_commune WHERE code_commune = ?", [code_commune])
    if not prix:
        raise HTTPException(404, f"Commune {code_commune} inconnue (aucune vente analysée)")
    rendement = db.query(
        "SELECT type_bien, loyer_m2, loyer_fiabilite, rendement_brut_pct, rendement_fiable "
        "FROM mart_rendement_locatif WHERE code_commune = ?", [code_commune])
    score = db.query(
        "SELECT type_bien, score_investissement, score_prix, score_rendement, "
        "score_dynamique_marche, score_dynamique_demo, score_services, score_tension "
        "FROM mart_score_investissement WHERE code_commune = ?", [code_commune])
    return {
        "code_commune": code_commune,
        "nom_commune": prix[0]["nom_commune"],
        "prix": prix,
        "rendement": rendement,
        "scores": score,
    }
