"""Endpoint tendances : séries trimestrielles pré-agrégées (2 mailles)."""

from typing import Literal

from fastapi import APIRouter, Query

from app import db
from app.cache import ttl_cache

router = APIRouter(prefix="/api/v1/tendances", tags=["tendances"])


@ttl_cache
def _tendances(departement, code_commune, type_bien, trimestre_min, trimestre_max):
    filtres = ["code_departement = ?"]
    params: list = [departement]
    if code_commune:
        filtres.append("maille = 'commune' AND code_commune = ?")
        params.append(code_commune)
    else:
        filtres.append("maille = 'departement'")
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    if trimestre_min:
        filtres.append("trimestre >= ?")
        params.append(trimestre_min)
    if trimestre_max:
        filtres.append("trimestre <= ?")
        params.append(trimestre_max)

    lignes = db.query(
        f"""SELECT maille, code_commune, nom_commune, type_bien, trimestre,
                   nb_ventes, prix_m2_median, prix_median, surface_mediane
            FROM mart_evolution_trimestrielle
            WHERE {' AND '.join(filtres)}
            ORDER BY trimestre, type_bien""",
        params,
    )
    return {"maille": "commune" if code_commune else "departement", "resultats": lignes}


@router.get("", summary="Évolution trimestrielle des prix et volumes")
def tendances(
    departement: str = Query("06", pattern=r"^(\d{2,3}|2A|2B)$"),
    code_commune: str | None = Query(None, pattern=r"^\d{5}$|^2[AB]\d{3}$",
                                     description="Si absent : maille département"),
    type_bien: Literal["appartement", "maison"] | None = None,
    trimestre_min: str | None = Query(None, pattern=r"^\d{4}Q[1-4]$", description="ex : 2022Q1"),
    trimestre_max: str | None = Query(None, pattern=r"^\d{4}Q[1-4]$"),
):
    return _tendances(departement, code_commune, type_bien, trimestre_min, trimestre_max)
