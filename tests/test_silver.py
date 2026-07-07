"""Tests des règles de nettoyage et d'enrichissement silver (hors-ligne)."""

import numpy as np
import pandas as pd
import pytest

from pipelines.silver import dvf_clean, enrichissement
from pipelines.silver.geocodage import adresse_texte
from pipelines.silver.referentiels import _num


def _vente(**kw):
    """Ligne DVF brute valide par défaut ; kw pour casser une règle à la fois."""
    base = {
        "id_mutation": "2024-1", "date_mutation": "2024-03-15",
        "nature_mutation": "Vente", "type_local": "Appartement",
        "valeur_fonciere": 250_000.0, "surface_reelle_bati": 50.0,
        "nombre_pieces_principales": "2", "surface_terrain": None,
        "adresse_numero": "12", "adresse_suffixe": None, "adresse_nom_voie": "RUE DE FRANCE",
        "code_postal": "06000", "code_commune": "06088", "nom_commune": "Nice",
        "code_departement": "06", "id_parcelle": "06088000AB0001",
        "longitude": 7.26, "latitude": 43.70,
    }
    base.update(kw)
    return base


class TestNettoyageDVF:
    def test_vente_valide_conservee(self):
        propres, stats = dvf_clean.nettoyer(pd.DataFrame([_vente()]))
        assert len(propres) == 1
        assert stats["brut"] == 1

    @pytest.mark.parametrize("casse", [
        {"nature_mutation": "Echange"},                    # R1
        {"type_local": "Dépendance"},                      # R2
        {"valeur_fonciere": 500.0},                        # R5 : prix < 10 k€
        {"valeur_fonciere": 25_000_000.0},                 # R5 : prix > 20 M€
        {"valeur_fonciere": None},                         # R5 : prix manquant
        {"surface_reelle_bati": 5.0},                      # R6 : surface < 8 m²
        {"valeur_fonciere": 15_000.0},                     # R7 : 300 €/m² aberrant
        {"code_commune": None},                            # R8
    ])
    def test_regles_excluent(self, casse):
        propres, _ = dvf_clean.nettoyer(pd.DataFrame([_vente(**casse)]))
        assert len(propres) == 0

    def test_r3_dedoublonnage_lots(self):
        # Même mutation/parcelle/prix répétée (lots) → 1 seule ligne
        df = pd.DataFrame([_vente(), _vente()])
        propres, _ = dvf_clean.nettoyer(df)
        assert len(propres) == 1

    def test_r4_mutation_multi_logements_exclue(self):
        # Une mutation vendant 2 appartements → prix global non ventilable → exclue
        df = pd.DataFrame([
            _vente(id_parcelle="06088000AB0001"),
            _vente(id_parcelle="06088000AB0002", surface_reelle_bati=72.0),
        ])
        propres, _ = dvf_clean.nettoyer(df)
        assert len(propres) == 0

    def test_normaliser_schema(self):
        propres, _ = dvf_clean.nettoyer(pd.DataFrame([_vente()]))
        out = dvf_clean.normaliser(propres)
        assert out.loc[out.index[0], "type_bien"] == "appartement"
        assert out.loc[out.index[0], "prix_m2"] == 5000.0
        assert out.loc[out.index[0], "trimestre"] == "2024Q1"
        assert out.loc[out.index[0], "geocode_source"] == "dvf"


class TestReferentiels:
    def test_num_virgule_francaise(self):
        s = pd.Series(["16,4580", "1 234,5", None, "12.5"])
        out = _num(s)
        assert out[0] == pytest.approx(16.458)
        assert out[1] == pytest.approx(1234.5)
        assert pd.isna(out[2])
        assert out[3] == pytest.approx(12.5)


class TestGeocodage:
    def test_adresse_texte(self):
        df = pd.DataFrame({"adresse_numero": ["12.0", None], "adresse_nom_voie": ["RUE DE FRANCE", "AV THIERS"]})
        out = adresse_texte(df)
        assert out.tolist() == ["12 RUE DE FRANCE", "AV THIERS"]


class TestEnrichissement:
    def test_projection_metres_ordres_de_grandeur(self):
        # 0.01° de latitude ≈ 1 112 m
        xy = enrichissement.projeter_metres(pd.Series([43.70, 43.71]), pd.Series([7.26, 7.26]))
        assert np.linalg.norm(xy[1] - xy[0]) == pytest.approx(1112, rel=0.01)

    def _ventes_geo(self):
        return pd.DataFrame({
            "type_bien": ["appartement"], "surface_bati": [50.0],
            "latitude": [43.7000], "longitude": [7.2600],
        })

    def test_compter_pois_rayon(self):
        pois = pd.DataFrame({
            "categorie": ["education", "education", "commerce"],
            # ~110 m au nord, ~5.5 km au nord, même point
            "latitude": [43.7010, 43.7500, 43.7000],
            "longitude": [7.2600, 7.2600, 7.2600],
        })
        out = enrichissement.compter_pois(self._ventes_geo(), pois)
        assert out.loc[0, "nb_education_500m"] == 1   # la 2e école est trop loin
        assert out.loc[0, "nb_commerce_500m"] == 1
        assert out.loc[0, "nb_transport_500m"] == 0

    def test_rapprochement_dpe(self):
        dpe = pd.DataFrame({
            "type_batiment": ["appartement", "appartement", "maison"],
            "surface_habitable_logement": [51.0, 90.0, 50.0],
            "latitude": [43.70005, 43.70005, 43.70005],   # tous à ~6 m
            "longitude": [7.26, 7.26, 7.26],
            "etiquette_dpe": ["C", "F", "G"],
            "etiquette_ges": ["C", "F", "G"],
            "conso_5_usages_par_m2_ep": [120.0, 300.0, 400.0],
        })
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        # Seul le 1er candidat matche : bon type ET surface à ±10 % (51 vs 50)
        assert out.loc[0, "etiquette_dpe"] == "C"
        assert out.loc[0, "dpe_distance_m"] < enrichissement.RAYON_DPE_M
        assert taux == 1.0

    def test_rapprochement_dpe_sans_candidat(self):
        dpe = pd.DataFrame({
            "type_batiment": ["appartement"], "surface_habitable_logement": [80.0],  # surface trop éloignée
            "latitude": [43.70005], "longitude": [7.26],
            "etiquette_dpe": ["D"], "etiquette_ges": ["D"], "conso_5_usages_par_m2_ep": [200.0],
        })
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert pd.isna(out.loc[0, "etiquette_dpe"])
        assert taux == 0.0
