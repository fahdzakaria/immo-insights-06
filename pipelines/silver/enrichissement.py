"""Silver enrichissement : la table de faits `ventes_enrichies`.

Chaque vente propre reçoit :
 1. le contexte communal (INSEE : population, niveau de vie, pauvreté… ;
    loyers de référence du bon segment) — jointure sur code commune ;
 2. l'accessibilité : nombre d'écoles / transports / commerces dans un rayon
    de 500 m (index spatial KDTree sur coordonnées projetées en mètres) ;
 3. son DPE probable, par RAPPROCHEMENT GÉOGRAPHIQUE : DPE de même type de
    bien à moins de 50 m avec surface à ±10 % — le candidat le plus proche
    (distance, puis écart de surface) gagne. Méthode assumée et documentée :
    DVF ne publie pas d'identifiant de logement, le rapprochement est donc
    probabiliste et le taux de couverture est tracé dans le manifeste.

Sortie : data/silver/ventes_enrichies/departement={dep}/ventes.parquet
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from pipelines.common import atomic_write_parquet, write_manifest
from pipelines.config import SILVER_DIR

logger = logging.getLogger("silver.enrichissement")

RAYON_POI_M = 500
RAYON_DPE_M = 50
TOLERANCE_SURFACE = 0.10


def projeter_metres(lat: pd.Series, lon: pd.Series) -> np.ndarray:
    """Projection équirectangulaire locale (précise à l'échelle d'un département)."""
    lat0 = np.deg2rad(np.nanmean(lat))
    x = np.deg2rad(lon) * 6_371_000 * np.cos(lat0)
    y = np.deg2rad(lat) * 6_371_000
    return np.column_stack([x, y])


def compter_pois(ventes: pd.DataFrame, pois: pd.DataFrame, rayon: float = RAYON_POI_M) -> pd.DataFrame:
    """Ajoute nb_{categorie}_500m à chaque vente géolocalisée."""
    ventes = ventes.copy()
    geo = ventes["latitude"].notna()
    xy_ventes = projeter_metres(ventes.loc[geo, "latitude"], ventes.loc[geo, "longitude"])

    for categorie in ("education", "transport", "commerce"):
        sub = pois[pois["categorie"] == categorie]
        col = f"nb_{categorie}_500m"
        # NA = vente non géolocalisée ; 0 = géolocalisée sans POI à proximité
        valeurs = pd.array([pd.NA] * len(ventes), dtype="Int32")
        valeurs[geo.to_numpy()] = 0
        if len(sub) and geo.any():
            tree = cKDTree(projeter_metres(sub["latitude"], sub["longitude"]))
            counts = tree.query_ball_point(xy_ventes, r=rayon, return_length=True)
            valeurs[geo.to_numpy()] = counts
        ventes[col] = valeurs
    return ventes


def rapprocher_dpe(ventes: pd.DataFrame, dpe: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Attache le DPE le plus vraisemblable à chaque vente ; retourne (df, taux de couverture)."""
    ventes = ventes.copy()
    for col in ("etiquette_dpe", "etiquette_ges"):
        ventes[col] = pd.Series(pd.NA, index=ventes.index, dtype="string")
    ventes["conso_ep_m2"] = np.nan
    ventes["dpe_distance_m"] = np.nan

    dpe_geo = dpe[dpe["latitude"].notna() & dpe["longitude"].notna()]
    matched_total = 0
    for type_bien in ("appartement", "maison"):
        v_mask = (ventes["type_bien"] == type_bien) & ventes["latitude"].notna()
        d_sub = dpe_geo[dpe_geo["type_batiment"] == type_bien].reset_index(drop=True)
        if not v_mask.any() or d_sub.empty:
            continue

        v_idx = ventes.index[v_mask]
        xy_v = projeter_metres(ventes.loc[v_idx, "latitude"], ventes.loc[v_idx, "longitude"])
        tree = cKDTree(projeter_metres(d_sub["latitude"], d_sub["longitude"]))
        voisins = tree.query_ball_point(xy_v, r=RAYON_DPE_M)

        surf_v = ventes.loc[v_idx, "surface_bati"].to_numpy()
        surf_d = d_sub["surface_habitable_logement"].to_numpy()
        xy_d = projeter_metres(d_sub["latitude"], d_sub["longitude"])

        for i, candidats in enumerate(voisins):
            if not candidats:
                continue
            cand = np.asarray(candidats)
            ecart_surface = np.abs(surf_d[cand] - surf_v[i]) / surf_v[i]
            ok = cand[ecart_surface <= TOLERANCE_SURFACE]
            if not len(ok):
                continue
            dist = np.linalg.norm(xy_d[ok] - xy_v[i], axis=1)
            best = ok[np.lexsort((np.abs(surf_d[ok] - surf_v[i]), dist))[0]]
            row = v_idx[i]
            ventes.at[row, "etiquette_dpe"] = d_sub.at[best, "etiquette_dpe"]
            ventes.at[row, "etiquette_ges"] = d_sub.at[best, "etiquette_ges"]
            ventes.at[row, "conso_ep_m2"] = d_sub.at[best, "conso_5_usages_par_m2_ep"]
            ventes.at[row, "dpe_distance_m"] = float(np.linalg.norm(xy_d[best] - xy_v[i]))
            matched_total += 1

    taux = matched_total / len(ventes) if len(ventes) else 0.0
    return ventes, taux


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
        logger.info("Enrichissement %s : DPE rapproché pour %.1f%% des ventes", dep, taux_dpe * 100)

        out = SILVER_DIR / "ventes_enrichies" / f"departement={dep}" / "ventes.parquet"
        atomic_write_parquet(ventes, out)
        write_manifest(out, source=f"silver dvf+insee+loyers+osm+dpe dep={dep}",
                       rows=len(ventes), extra={"taux_rapprochement_dpe": round(taux_dpe, 4)})
        logger.info("Ventes enrichies %s : %d lignes, %d colonnes → %s",
                    dep, len(ventes), ventes.shape[1], out)
        produced.append(out)
    return produced
