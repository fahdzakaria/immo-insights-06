"""Silver enrichissement : la table de faits `ventes_enrichies`.

Chaque vente propre reçoit :
 1. le contexte communal (INSEE : population, niveau de vie, pauvreté… ;
    loyers de référence du bon segment) — jointure sur code commune ;
 2. l'accessibilité : nombre d'écoles / transports / commerces dans un rayon
    de 500 m (index spatial KDTree sur coordonnées projetées en mètres) ;
 3. son DPE probable, par RAPPROCHEMENT GÉOGRAPHIQUE : DPE de même type de
    bien à moins de 50 m, de surface à ±10 %, établi avant la vente — le
    candidat le plus proche (distance, puis écart de surface) gagne. DVF ne
    publie pas d'identifiant de logement : le rapprochement est probabiliste.
    Quand plusieurs candidats portent des étiquettes différentes (même
    immeuble), la vente est marquée `dpe_ambigu` et exclue des analyses par
    étiquette. Taux de couverture et d'ambiguïté tracés dans le manifeste ;
 4. son QUARTIER (IRIS INSEE) : point dans polygone sur les contours IGN,
    limité aux IRIS de la commune de la vente. Taux tracé dans le manifeste.

Sortie : data/silver/ventes_enrichies/departement={dep}/ventes.parquet
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import BRONZE_DIR, SILVER_DIR

logger = logging.getLogger("silver.enrichissement")

RAYON_POI_M = 500
RAYON_DPE_M = 50
TOLERANCE_SURFACE = 0.10
# Un DPE établi APRÈS la vente décrit l'état du logement après travaux ou une
# vente/location ultérieure : on n'accepte que les DPE existant à la vente
# (tolérance : l'acte peut précéder de quelques jours l'enregistrement du DPE).
TOLERANCE_DATE_DPE_JOURS = 30
RAYON_TERRE_M = 6_371_000


def latitude_reference(lat: pd.Series) -> float:
    """Latitude de référence (radians) de la projection : moyenne des ventes."""
    return float(np.deg2rad(np.nanmean(lat)))


def projeter_metres(lat: pd.Series, lon: pd.Series, lat0: float) -> np.ndarray:
    """Projection équirectangulaire locale (précise à l'échelle d'un département).

    `lat0` (radians) est OBLIGATOIRE et doit être le même pour tous les jeux de
    points que l'on compare : x = lon × R × cos(lat0), donc deux lat0 différents
    décalent les points de plusieurs centaines de mètres d'est en ouest.
    """
    x = np.deg2rad(np.asarray(lon, dtype=float)) * RAYON_TERRE_M * np.cos(lat0)
    y = np.deg2rad(np.asarray(lat, dtype=float)) * RAYON_TERRE_M
    return np.column_stack([x, y])


def compter_pois(ventes: pd.DataFrame, pois: pd.DataFrame, rayon: float = RAYON_POI_M) -> pd.DataFrame:
    """Ajoute nb_{categorie}_500m à chaque vente géolocalisée."""
    ventes = ventes.copy()
    geo = ventes["latitude"].notna()
    lat0 = latitude_reference(ventes.loc[geo, "latitude"]) if geo.any() else 0.0
    xy_ventes = projeter_metres(ventes.loc[geo, "latitude"], ventes.loc[geo, "longitude"], lat0)

    for categorie in ("education", "transport", "commerce"):
        sub = pois[pois["categorie"] == categorie]
        col = f"nb_{categorie}_500m"
        # NA = vente non géolocalisée ; 0 = géolocalisée sans POI à proximité
        valeurs = pd.array([pd.NA] * len(ventes), dtype="Int32")
        valeurs[geo.to_numpy()] = 0
        if len(sub) and geo.any():
            tree = cKDTree(projeter_metres(sub["latitude"], sub["longitude"], lat0))
            counts = tree.query_ball_point(xy_ventes, r=rayon, return_length=True)
            valeurs[geo.to_numpy()] = counts
        ventes[col] = valeurs
    return ventes


def rapprocher_dpe(ventes: pd.DataFrame, dpe: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Attache le DPE le plus vraisemblable à chaque vente ; retourne (df, taux de couverture).

    Candidats : DPE du même type de bien, à moins de RAYON_DPE_M, de surface à
    ±TOLERANCE_SURFACE, établi avant la vente. Le plus proche gagne (distance,
    puis écart de surface). Colonnes ajoutées :
      - etiquette_dpe / etiquette_ges / conso_ep_m2 / dpe_distance_m / dpe_date ;
      - dpe_nb_candidats : nombre de DPE plausibles ;
      - dpe_ambigu : True si ces candidats n'ont pas tous la même étiquette
        (cas courant en immeuble : plusieurs appartements de même surface).
        Les analyses par étiquette ne gardent que les rapprochements non ambigus.
    """
    ventes = ventes.copy()
    for col in ("etiquette_dpe", "etiquette_ges"):
        ventes[col] = pd.Series(pd.NA, index=ventes.index, dtype="string")
    ventes["conso_ep_m2"] = np.nan
    ventes["dpe_distance_m"] = np.nan
    ventes["dpe_date"] = pd.Series(pd.NaT, index=ventes.index, dtype="datetime64[ns]")
    ventes["dpe_nb_candidats"] = pd.array([0] * len(ventes), dtype="Int32")
    ventes["dpe_ambigu"] = pd.array([pd.NA] * len(ventes), dtype="boolean")

    geo = ventes["latitude"].notna()
    if not geo.any():
        return ventes, 0.0
    lat0 = latitude_reference(ventes.loc[geo, "latitude"])  # même projection pour ventes ET DPE

    dpe_geo = dpe[dpe["latitude"].notna() & dpe["longitude"].notna()]
    # Sans date de DPE on ne peut pas vérifier qu'il existait à la vente : écarté
    dpe_geo = dpe_geo[dpe_geo["date_etablissement_dpe"].notna()]
    matched_total = 0
    for type_bien in ("appartement", "maison"):
        v_mask = (ventes["type_bien"] == type_bien) & geo
        d_sub = dpe_geo[dpe_geo["type_batiment"] == type_bien].reset_index(drop=True)
        if not v_mask.any() or d_sub.empty:
            continue

        v_idx = ventes.index[v_mask]
        xy_v = projeter_metres(ventes.loc[v_idx, "latitude"], ventes.loc[v_idx, "longitude"], lat0)
        xy_d = projeter_metres(d_sub["latitude"], d_sub["longitude"], lat0)
        voisins = cKDTree(xy_d).query_ball_point(xy_v, r=RAYON_DPE_M)

        surf_v = ventes.loc[v_idx, "surface_bati"].to_numpy(dtype=float)
        surf_d = d_sub["surface_habitable_logement"].to_numpy(dtype=float)
        date_v = pd.to_datetime(ventes.loc[v_idx, "date_mutation"]).to_numpy().astype("datetime64[D]")
        date_d = pd.to_datetime(d_sub["date_etablissement_dpe"]).to_numpy().astype("datetime64[D]")
        etiquettes = d_sub["etiquette_dpe"].to_numpy(dtype=object)
        tolerance = np.timedelta64(TOLERANCE_DATE_DPE_JOURS, "D")

        for i, candidats in enumerate(voisins):
            if not candidats:
                continue
            cand = np.asarray(candidats)
            ok = cand[
                (np.abs(surf_d[cand] - surf_v[i]) / surf_v[i] <= TOLERANCE_SURFACE)
                & (date_d[cand] <= date_v[i] + tolerance)
            ]
            if not len(ok):
                continue
            dist = np.linalg.norm(xy_d[ok] - xy_v[i], axis=1)
            ordre = np.lexsort((np.abs(surf_d[ok] - surf_v[i]), dist))
            best = ok[ordre[0]]
            row = v_idx[i]
            ventes.at[row, "etiquette_dpe"] = d_sub.at[best, "etiquette_dpe"]
            ventes.at[row, "etiquette_ges"] = d_sub.at[best, "etiquette_ges"]
            ventes.at[row, "conso_ep_m2"] = d_sub.at[best, "conso_5_usages_par_m2_ep"]
            ventes.at[row, "dpe_distance_m"] = float(dist[ordre[0]])
            ventes.at[row, "dpe_date"] = d_sub.at[best, "date_etablissement_dpe"]
            ventes.at[row, "dpe_nb_candidats"] = len(ok)
            ventes.at[row, "dpe_ambigu"] = len(set(etiquettes[ok])) > 1
            matched_total += 1

    taux = matched_total / len(ventes) if len(ventes) else 0.0
    return ventes, taux


def rattacher_iris(ventes: pd.DataFrame, contours: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attache à chaque vente son quartier IRIS (colonnes `code_iris`, `nom_iris`).

    Point dans polygone, directement en longitude/latitude : ventes et contours
    sont dans le même repère (WGS84) et l'appartenance à un polygone ne dépend
    pas d'une projection — aucune latitude de référence n'entre en jeu ici.

    Une vente n'est rattachée qu'à un IRIS de SA commune (code INSEE de DVF).
    Si son point tombe dans le quartier d'une autre commune, c'est que le
    géocodage est douteux (adresse en limite communale, homonyme de voie) :
    on préfère ne pas lui donner de quartier plutôt qu'un quartier faux.

    Restent sans quartier (NA) : ventes non géolocalisées, points hors de tout
    contour de leur commune. Retourne (df, stats) ; stats alimente le manifeste.
    """
    ventes = ventes.copy()
    ventes["code_iris"] = pd.Series(pd.NA, index=ventes.index, dtype="string")
    ventes["nom_iris"] = pd.Series(pd.NA, index=ventes.index, dtype="string")
    stats = {"nb_rattachees": 0, "nb_hors_commune": 0, "taux_rattachement_iris": 0.0}

    geo = (ventes["latitude"].notna() & ventes["longitude"].notna()).to_numpy()
    if not geo.any() or contours.empty:
        return ventes, stats

    # Tri par code : si deux contours se recouvrent, le plus petit code gagne (déterministe)
    contours = contours.sort_values("code_iris", ignore_index=True)
    polygones = shapely.from_geojson(contours["geometrie_geojson"].to_numpy())
    arbre = shapely.STRtree(polygones)

    positions = np.flatnonzero(geo)
    points = shapely.points(
        ventes["longitude"].to_numpy(dtype=float)[positions],
        ventes["latitude"].to_numpy(dtype=float)[positions],
    )
    # « intersects » plutôt que « within » : un point posé exactement sur une
    # frontière garde un quartier (le plus petit code, voir le tri ci-dessus)
    i_point, i_poly = arbre.query(points, predicate="intersects")

    commune_vente = ventes["code_commune"].astype("string").to_numpy(dtype=object)[positions[i_point]]
    commune_iris = contours["code_commune"].astype("string").to_numpy(dtype=object)[i_poly]
    meme_commune = commune_vente == commune_iris

    # Un point par vente : on garde le premier IRIS (ordre des codes) de sa commune
    ordre = np.lexsort((i_poly[meme_commune], i_point[meme_commune]))
    p_ok, poly_ok = i_point[meme_commune][ordre], i_poly[meme_commune][ordre]
    premier = np.concatenate(([True], p_ok[1:] != p_ok[:-1])) if len(p_ok) else np.array([], dtype=bool)
    p_ok, poly_ok = p_ok[premier], poly_ok[premier]

    lignes = ventes.index[positions[p_ok]]
    ventes.loc[lignes, "code_iris"] = contours["code_iris"].to_numpy(dtype=object)[poly_ok]
    ventes.loc[lignes, "nom_iris"] = contours["nom_iris"].to_numpy(dtype=object)[poly_ok]

    # Points tombés uniquement dans des IRIS d'une AUTRE commune
    hors = np.setdiff1d(i_point[~meme_commune], p_ok)
    stats = {
        "nb_rattachees": int(len(p_ok)),
        "nb_hors_commune": int(len(hors)),
        "taux_rattachement_iris": round(len(p_ok) / len(ventes), 4) if len(ventes) else 0.0,
    }
    return ventes, stats


def lire_contours_iris(dep: str) -> pd.DataFrame:
    """Contours IRIS bronze du département (ingestion : pipelines/ingestion/iris.py)."""
    return pd.read_parquet(BRONZE_DIR / "iris" / f"departement={dep}" / "contours.parquet")


def build(departements: list[str]) -> list[Path]:
    insee = pd.read_parquet(SILVER_DIR / "insee" / "communes.parquet")
    loyers = pd.read_parquet(SILVER_DIR / "loyers" / "communes.parquet").drop(columns=["nom_commune"])

    produced = []
    for dep in departements:
        ventes = pd.read_parquet(SILVER_DIR / "dvf" / f"departement={dep}" / "ventes.parquet")
        pois = pd.read_parquet(SILVER_DIR / "osm" / f"departement={dep}" / "pois.parquet")
        dpe = pd.read_parquet(SILVER_DIR / "dpe" / f"departement={dep}" / "dpe.parquet")

        # 1. Contexte communal
        ventes = ventes.merge(insee, on="code_commune", how="left")
        ventes = ventes.merge(loyers, on="code_commune", how="left")
        # Loyer de référence du bon segment (appartement vs maison)
        ventes["loyer_m2_ref"] = np.where(
            ventes["type_bien"] == "maison",
            ventes["loyer_m2_maison"],
            ventes["loyer_m2_appartement"],
        )

        # 2. Accessibilité POI
        ventes = compter_pois(ventes, pois)

        # 3. Rapprochement DPE
        ventes, taux_dpe = rapprocher_dpe(ventes, dpe)
        nb_non_ambigus = int((ventes["dpe_ambigu"] == False).sum())  # noqa: E712 (colonne nullable)
        logger.info("Enrichissement %s : DPE rapproché pour %.1f%% des ventes, dont %d sans ambiguïté",
                    dep, taux_dpe * 100, nb_non_ambigus)

        # 4. Quartier IRIS
        ventes, stats_iris = rattacher_iris(ventes, lire_contours_iris(dep))
        logger.info("Enrichissement %s : quartier IRIS pour %.2f%% des ventes (%d écartées : point hors commune)",
                    dep, stats_iris["taux_rattachement_iris"] * 100, stats_iris["nb_hors_commune"])

        out = SILVER_DIR / "ventes_enrichies" / f"departement={dep}" / "ventes.parquet"
        atomic_write_parquet(ventes, out)
        write_manifest(out, source=f"silver dvf+insee+loyers+osm+dpe+iris dep={dep}",
                       rows=len(ventes), extra={"taux_rapprochement_dpe": round(taux_dpe, 4),
                              "nb_dpe_non_ambigus": nb_non_ambigus, **stats_iris})
        logger.info("Ventes enrichies %s : %d lignes, %d colonnes → %s",
                    dep, len(ventes), ventes.shape[1], out)
        produced.append(out)
    return produced
