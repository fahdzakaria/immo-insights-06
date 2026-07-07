"""Endpoints marché : KPIs d'ensemble, impact DPE, métadonnées."""

from typing import Literal

from fastapi import APIRouter, Query

from app import db
from app.cache import ttl_cache

router = APIRouter(prefix="/api/v1", tags=["marché"])

DEP = Query("06", pattern=r"^(\d{2,3}|2A|2B)$")


@router.get("/meta", summary="Métadonnées : départements, période couverte, marts disponibles")
@ttl_cache
def meta():
    deps = db.query(
        "SELECT DISTINCT code_departement FROM mart_prix_m2_par_commune ORDER BY 1")
    trimestres = db.query_one(
        "SELECT min(trimestre) AS premier, max(trimestre) AS dernier FROM mart_evolution_trimestrielle")
    return {
        "departements": [d["code_departement"] for d in deps],
        "premier_trimestre": trimestres["premier"],
        "dernier_trimestre": trimestres["dernier"],
        "marts": db.marts_disponibles(),
    }


@ttl_cache
def _kpis(departement: str):
    # Maille département du mart trimestriel : volumes et prix
    global_ = db.query_one(
        """SELECT sum(nb_ventes) AS nb_ventes_total,
                  min(trimestre) AS premier_trimestre,
                  max(trimestre) AS dernier_trimestre
           FROM mart_evolution_trimestrielle
           WHERE maille = 'departement' AND code_departement = ?""",
        [departement],
    )
    # Prix médian pondéré sur les 4 derniers trimestres, par type de bien
    recents = db.query(
        """WITH derniers AS (
             SELECT DISTINCT trimestre FROM mart_evolution_trimestrielle
             WHERE code_departement = ? ORDER BY trimestre DESC LIMIT 4
           )
           SELECT type_bien,
                  sum(nb_ventes) AS nb_ventes_12m,
                  round(sum(prix_m2_median * nb_ventes) / sum(nb_ventes), 0) AS prix_m2_median_12m
           FROM mart_evolution_trimestrielle
           WHERE maille = 'departement' AND code_departement = ?
             AND trimestre IN (SELECT trimestre FROM derniers)
           GROUP BY type_bien ORDER BY type_bien""",
        [departement, departement],
    )
    evolution = db.query(
        """SELECT type_bien,
                  round(median(evolution_1an_pct), 2) AS evolution_1an_pct_mediane,
                  round(median(evolution_3ans_pct), 2) AS evolution_3ans_pct_mediane
           FROM mart_prix_m2_par_commune
           WHERE code_departement = ? GROUP BY type_bien ORDER BY type_bien""",
        [departement],
    )
    rendement = db.query_one(
        """SELECT round(median(rendement_brut_pct), 2) AS rendement_brut_median,
                  count(rendement_brut_pct) AS nb_communes_avec_rendement
           FROM mart_rendement_locatif WHERE code_departement = ?""",
        [departement],
    )
    nb_communes = db.query_one(
        "SELECT count(DISTINCT code_commune) AS n FROM mart_prix_m2_par_commune WHERE code_departement = ?",
        [departement],
    )
    return {
        "departement": departement,
        "nb_ventes_total": global_["nb_ventes_total"],
        "periode": [global_["premier_trimestre"], global_["dernier_trimestre"]],
        "nb_communes": nb_communes["n"],
        "par_type_bien": recents,
        "evolutions": evolution,
        "rendement_brut_median": rendement["rendement_brut_median"],
    }


@router.get("/kpis", summary="KPIs d'ensemble du marché (vue overview)")
def kpis(departement: str = DEP):
    return _kpis(departement)


@ttl_cache
def _impact_dpe(departement, type_bien):
    filtres, params = ["code_departement = ?"], [departement]
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    return {"resultats": db.query(
        f"""SELECT type_bien, etiquette_dpe, nb_ventes, prix_m2_median,
                   ecart_vs_marche_pct, conso_ep_m2_mediane
            FROM mart_impact_dpe WHERE {' AND '.join(filtres)}
            ORDER BY type_bien, etiquette_dpe""",
        params,
    )}


@router.get("/dpe/impact", summary="Décote/surcote énergétique par étiquette (à marché local neutralisé)")
def impact_dpe(departement: str = DEP,
               type_bien: Literal["appartement", "maison"] | None = None):
    return _impact_dpe(departement, type_bien)
