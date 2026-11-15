"""Endpoints investissement : rendement locatif, opportunités (score), estimateur."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.cache import ttl_cache

router = APIRouter(prefix="/api/v1", tags=["investissement"])

DEP = Query("06", pattern=r"^(\d{2,3}|2A|2B)$")

# En dessous, une médiane communale ne dit rien : pas d'estimation
SEUIL_VENTES_ESTIMATION = 5
# Niveaux de fiabilité de l'estimation selon le nombre de ventes sur 24 mois
SEUIL_FIABILITE_CORRECTE = 20
SEUIL_FIABILITE_BONNE = 100
METHODES = {
    "commune": "médiane communale 24 mois × ajustement DPE départemental (quartiles locaux)",
    "quartier": "médiane du quartier IRIS 24 mois × ajustement DPE départemental (quartiles du quartier)",
}

TRIS_RENDEMENT = {"rendement": "rendement_brut_pct", "prix_m2": "prix_m2_median", "loyer": "loyer_m2"}


@ttl_cache
def _rendement(departement, type_bien, rendement_min, prix_m2_max, loyer_fiable, tri, ordre, limit, offset):
    filtres, params = ["code_departement = ?"], [departement]
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    if rendement_min is not None:
        filtres.append("rendement_brut_pct >= ?")
        params.append(rendement_min)
    if prix_m2_max is not None:
        filtres.append("prix_m2_median <= ?")
        params.append(prix_m2_max)
    if loyer_fiable:
        filtres.append("rendement_fiable")
    where = " AND ".join(filtres)
    total = db.query_one(f"SELECT count(*) AS n FROM mart_rendement_locatif WHERE {where}", params)["n"]
    lignes = db.query(
        f"""SELECT * FROM mart_rendement_locatif WHERE {where}
            ORDER BY {TRIS_RENDEMENT[tri]} {"DESC" if ordre == "desc" else "ASC"} NULLS LAST
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    return {"total": total, "limit": limit, "offset": offset, "resultats": lignes}


@router.get("/rendement", summary="Rendement locatif brut par commune, filtrable")
def rendement(
    departement: str = DEP,
    type_bien: Literal["appartement", "maison"] | None = None,
    rendement_min: float | None = Query(None, ge=0, le=30),
    prix_m2_max: float | None = Query(None, ge=0),
    loyer_fiable: bool = Query(False, description="Seulement les loyers prédits à l'échelle de la commune, ≥ 20 ventes"),
    tri: Literal["rendement", "prix_m2", "loyer"] = "rendement",
    ordre: Literal["asc", "desc"] = "desc",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return _rendement(departement, type_bien, rendement_min, prix_m2_max, loyer_fiable, tri, ordre, limit, offset)


@ttl_cache
def _opportunites(departement, type_bien, score_min, prix_m2_max, loyer_fiable, limit):
    filtres, params = ["code_departement = ?"], [departement]
    if type_bien:
        filtres.append("type_bien = ?")
        params.append(type_bien)
    if score_min is not None:
        filtres.append("score_investissement >= ?")
        params.append(score_min)
    if prix_m2_max is not None:
        filtres.append("prix_m2_median <= ?")
        params.append(prix_m2_max)
    if loyer_fiable:
        filtres.append("rendement_fiable")
    return {"resultats": db.query(
        f"""SELECT * FROM mart_score_investissement
            WHERE {' AND '.join(filtres)}
            ORDER BY score_investissement DESC LIMIT ?""",
        params + [limit],
    )}


@router.get("/opportunites", summary="Opportunités d'investissement (score composite 0-100)")
def opportunites(
    departement: str = DEP,
    type_bien: Literal["appartement", "maison"] | None = None,
    score_min: float | None = Query(None, ge=0, le=100),
    prix_m2_max: float | None = Query(None, ge=0),
    loyer_fiable: bool = Query(False, description="Écarte les communes dont le rendement repose sur un loyer extrapolé"),
    limit: int = Query(50, ge=1, le=200),
):
    return _opportunites(departement, type_bien, score_min, prix_m2_max, loyer_fiable, limit)


@router.get("/estimation", summary="Estimation du prix d'un bien (médiane locale ajustée DPE)")
def estimation(
    code_commune: str = Query(..., pattern=r"^\d{5}$|^2[AB]\d{3}$"),
    type_bien: Literal["appartement", "maison"] = "appartement",
    surface: float = Query(..., gt=8, lt=1000),
    etiquette_dpe: Literal["A", "B", "C", "D", "E", "F", "G"] | None = None,
    code_iris: str | None = Query(None, pattern=r"^\d{9}$|^2[AB]\d{7}$",
                                  description="Quartier IRIS (facultatif) : affine la référence de prix"),
):
    """Méthode transparente (pas un modèle ML) :
    prix = surface × prix médian €/m² local (24 mois) — celui du quartier IRIS
    s'il est demandé et compte au moins 5 ventes, sinon celui de la commune —,
    ajusté de la décote/surcote DPE observée dans le département,
    fourchette = quartiles p25/p75 de la même maille.

    Garde-fous : pas d'estimation sous 5 ventes sur 24 mois ; un quartier sous
    ce seuil retombe sur la commune, en le disant ; l'écart DPE n'est appliqué
    que s'il est statistiquement fiable (mart_impact_dpe.fiable)."""
    base = db.query_one(
        """SELECT nom_commune, code_departement, prix_m2_median, prix_m2_p25, prix_m2_p75, nb_ventes_24m
           FROM mart_prix_m2_par_commune WHERE code_commune = ? AND type_bien = ?""",
        [code_commune, type_bien],
    )
    # Le quartier est validé AVANT le seuil de la commune : une requête
    # incohérente (quartier d'une autre commune) répond toujours 422
    quartier = None
    if code_iris:
        quartier = db.query_one(
            """SELECT nom_iris, code_commune, prix_m2_median, prix_m2_p25, prix_m2_p75, nb_ventes_24m
               FROM mart_prix_m2_par_quartier WHERE code_iris = ? AND type_bien = ?""",
            [code_iris, type_bien],
        )
        if quartier is None:
            raise HTTPException(404, f"Quartier {code_iris} inconnu")
        if quartier["code_commune"] != code_commune:
            raise HTTPException(422, f"Le quartier {code_iris} n'appartient pas à la commune {code_commune}")
    if (base is None or base["prix_m2_median"] is None or base["prix_m2_p25"] is None
            or base["prix_m2_p75"] is None or (base["nb_ventes_24m"] or 0) < SEUIL_VENTES_ESTIMATION):
        raise HTTPException(404, "Pas assez de ventes récentes dans cette commune pour estimer")

    # Référence : la commune par défaut, le quartier s'il est demandé et assez fourni
    reference = base
    maille = "commune"
    nom_iris = None
    motif_quartier = None
    if quartier:
        nom_iris = quartier["nom_iris"]
        if (quartier["prix_m2_median"] is None or quartier["prix_m2_p25"] is None
                or quartier["prix_m2_p75"] is None or quartier["nb_ventes_24m"] < SEUIL_VENTES_ESTIMATION):
            motif_quartier = (f"moins de {SEUIL_VENTES_ESTIMATION} ventes sur 24 mois dans ce quartier "
                              "pour ce type de bien : référence de la commune utilisée")
        else:
            reference = quartier
            maille = "quartier"

    ajustement_pct = 0.0
    ajustement_applique = False
    motif = None
    if etiquette_dpe:
        dpe = db.query_one(
            """SELECT ecart_vs_marche_pct, fiable FROM mart_impact_dpe
               WHERE code_departement = ? AND type_bien = ? AND etiquette_dpe = ?""",
            [base["code_departement"], type_bien, etiquette_dpe],
        )
        if dpe and dpe["fiable"] and dpe["ecart_vs_marche_pct"] is not None:
            ajustement_pct = dpe["ecart_vs_marche_pct"]
            ajustement_applique = True
        else:
            motif = "écart DPE non appliqué : non significatif pour cette étiquette (trop peu de ventes ou écart trop incertain)"

    nb_ventes = reference["nb_ventes_24m"]
    niveau = ("bonne" if nb_ventes >= SEUIL_FIABILITE_BONNE
              else "correcte" if nb_ventes >= SEUIL_FIABILITE_CORRECTE else "faible")
    facteur = 1 + ajustement_pct / 100
    return {
        "code_commune": code_commune,
        "nom_commune": base["nom_commune"],
        "type_bien": type_bien,
        "surface": surface,
        "etiquette_dpe": etiquette_dpe,
        "code_iris": code_iris,
        "nom_iris": nom_iris,
        "maille": maille,
        "maille_motif": motif_quartier,
        "prix_m2_reference": reference["prix_m2_median"],
        "ajustement_dpe_pct": ajustement_pct,
        "ajustement_dpe_applique": ajustement_applique,
        "ajustement_dpe_motif": motif,
        "prix_estime": round(surface * reference["prix_m2_median"] * facteur),
        "fourchette_basse": round(surface * reference["prix_m2_p25"] * facteur),
        "fourchette_haute": round(surface * reference["prix_m2_p75"] * facteur),
        "fiabilite": {
            "nb_ventes_24m": nb_ventes,
            "niveau": niveau,
            "methode": METHODES[maille],
        },
    }
