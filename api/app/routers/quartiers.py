"""Endpoint quartiers : prix au m² par quartier IRIS (maille infra-communale).

Ne concerne que les communes découpées en quartiers par l'INSEE. Les lignes
sous 5 ventes sur 24 mois existent (la carte dessine le quartier) mais leurs
prix sont déjà NULL dans le mart : aucun garde-fou à refaire ici.
"""

from typing import Literal

from fastapi import APIRouter, Query

from app import db
from app.cache import ttl_cache

router = APIRouter(prefix="/api/v1/quartiers", tags=["quartiers"])

# Tri par LISTE BLANCHE : jamais de colonne injectée par l'utilisateur
TRIS = {
    "prix_m2": "prix_m2_median",
    "ventes": "nb_ventes_24m",
    "evolution": "evolution_1an_pct",
    "ecart": "ecart_commune_pct",
    "nom": "nom_iris",
}


@ttl_cache
def _liste(departement, code_commune, type_bien, fiable, tri, ordre, limit, offset):
    filtres, params = ["code_departement = ?"], [departement]
    if code_commune:
        filtres.append("code_commune = ?")
        params.append(code_commune)
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    if fiable:
        filtres.append("fiable")

    where = " AND ".join(filtres)
    total = db.query_one(f"SELECT count(*) AS n FROM mart_prix_m2_par_quartier WHERE {where}", params)["n"]
    lignes = db.query(
        f"""SELECT * FROM mart_prix_m2_par_quartier
            WHERE {where}
            ORDER BY {TRIS[tri]} {"DESC" if ordre == "desc" else "ASC"} NULLS LAST
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    return {"total": total, "limit": limit, "offset": offset, "resultats": lignes}


@router.get("", summary="Quartiers IRIS avec prix au m² (carte au zoom, estimateur)")
def liste_quartiers(
    departement: str = Query("06", pattern=r"^(\d{2,3}|2A|2B)$"),
    code_commune: str | None = Query(None, pattern=r"^(\d{5}|2[AB]\d{3})$"),
    type_bien: Literal["appartement", "maison"] | None = None,
    fiable: bool = Query(False, description="Seulement les quartiers à 20 ventes ou plus sur 24 mois"),
    tri: Literal["prix_m2", "ventes", "evolution", "ecart", "nom"] = "ventes",
    ordre: Literal["asc", "desc"] = "desc",
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    return _liste(departement, code_commune, type_bien, fiable, tri, ordre, limit, offset)
