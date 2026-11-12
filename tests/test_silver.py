"""Tests des règles de nettoyage et d'enrichissement silver (hors-ligne)."""

import numpy as np
import pandas as pd
import pytest

from pipelines.silver import dvf_clean, enrichissement
from pipelines.silver.geocodage import adresse_texte
from pipelines.silver.referentiels import INSEE_MESURES, _num, pivoter_insee


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
        lat0 = enrichissement.latitude_reference(pd.Series([43.70, 43.71]))
        xy = enrichissement.projeter_metres(pd.Series([43.70, 43.71]), pd.Series([7.26, 7.26]), lat0)
        assert np.linalg.norm(xy[1] - xy[0]) == pytest.approx(1112, rel=0.01)

    def _ventes_geo(self):
        return pd.DataFrame({
            "type_bien": ["appartement"], "surface_bati": [50.0],
            "latitude": [43.7000], "longitude": [7.2600],
            "date_mutation": pd.to_datetime(["2024-06-15"]),
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

    def test_compter_pois_insensible_aux_pois_lointains(self):
        """Non-régression du bug de projection côté POI.

        Une école à ~450 m à l'est de la vente doit être comptée même si le jeu
        de POI contient un point très au nord. Avant, la latitude de référence
        était calculée séparément pour les ventes et pour les POI : ce point
        lointain décalait toutes les écoles de plus de 2 km vers l'ouest."""
        pois = pd.DataFrame({
            "categorie": ["education", "education"],
            "latitude": [43.7000, 44.2000],     # même latitude que la vente ; ~55 km au nord
            "longitude": [7.2656, 7.2600],      # ~450 m à l'est
        })
        out = enrichissement.compter_pois(self._ventes_geo(), pois)
        assert out.loc[0, "nb_education_500m"] == 1

    def test_rapprochement_dpe(self):
        dpe = pd.DataFrame({
            "type_batiment": ["appartement", "appartement", "maison"],
            "surface_habitable_logement": [51.0, 90.0, 50.0],
            "latitude": [43.70005, 43.70005, 43.70005],   # tous à ~6 m
            "longitude": [7.26, 7.26, 7.26],
            "etiquette_dpe": ["C", "F", "G"],
            "etiquette_ges": ["C", "F", "G"],
            "conso_5_usages_par_m2_ep": [120.0, 300.0, 400.0],
            "date_etablissement_dpe": pd.to_datetime(["2024-03-01"] * 3),
        })
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        # Seul le 1er candidat matche : bon type ET surface à ±10 % (51 vs 50)
        assert out.loc[0, "etiquette_dpe"] == "C"
        assert out.loc[0, "dpe_distance_m"] < enrichissement.RAYON_DPE_M
        assert out.loc[0, "dpe_nb_candidats"] == 1 and out.loc[0, "dpe_ambigu"] == False  # noqa: E712
        assert taux == 1.0

    def _dpe(self, **colonnes):
        base = {
            "type_batiment": ["appartement"], "surface_habitable_logement": [50.0],
            "latitude": [43.70005], "longitude": [7.26],
            "etiquette_dpe": ["D"], "etiquette_ges": ["D"], "conso_5_usages_par_m2_ep": [200.0],
            "date_etablissement_dpe": pd.to_datetime(["2024-03-01"]),
        }
        base.update(colonnes)
        return pd.DataFrame(base)

    def test_rapprochement_insensible_aux_autres_points(self):
        """Régression du bug de projection : un DPE lointain dans le jeu de
        données ne doit pas déplacer les autres (avant : décalage de 200-700 m,
        donc aucun rapprochement possible à 50 m)."""
        dpe = self._dpe(
            type_batiment=["appartement"] * 2, surface_habitable_logement=[50.0, 50.0],
            latitude=[43.70005, 44.20], longitude=[7.26, 6.70],   # le 2e est à ~70 km
            etiquette_dpe=["D", "A"], etiquette_ges=["D", "A"], conso_5_usages_par_m2_ep=[200.0, 40.0],
            date_etablissement_dpe=pd.to_datetime(["2024-03-01"] * 2),
        )
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert out.loc[0, "etiquette_dpe"] == "D"
        assert out.loc[0, "dpe_distance_m"] == pytest.approx(5.6, abs=0.5)

    def test_dpe_posterieur_a_la_vente_ecarte(self):
        """Un DPE refait un an après la vente décrit un autre état du logement."""
        dpe = self._dpe(date_etablissement_dpe=pd.to_datetime(["2025-06-15"]))
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert pd.isna(out.loc[0, "etiquette_dpe"]) and taux == 0.0
        # Tolérance de 30 jours : un DPE enregistré juste après l'acte reste accepté
        dpe = self._dpe(date_etablissement_dpe=pd.to_datetime(["2024-07-01"]))
        out, _ = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert out.loc[0, "etiquette_dpe"] == "D"

    def test_dpe_sans_date_ecarte(self):
        dpe = self._dpe(date_etablissement_dpe=pd.to_datetime([None]))
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert taux == 0.0

    def test_candidats_aux_etiquettes_differentes_marques_ambigus(self):
        """Même immeuble, même surface, étiquettes D et G : impossible de trancher."""
        dpe = self._dpe(
            type_batiment=["appartement"] * 2, surface_habitable_logement=[50.0, 50.5],
            latitude=[43.70005, 43.70006], longitude=[7.26, 7.26],
            etiquette_dpe=["D", "G"], etiquette_ges=["D", "G"], conso_5_usages_par_m2_ep=[200.0, 450.0],
            date_etablissement_dpe=pd.to_datetime(["2024-03-01", "2023-01-10"]),
        )
        out, _ = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert out.loc[0, "etiquette_dpe"] == "D"          # le plus proche reste affiché
        assert out.loc[0, "dpe_nb_candidats"] == 2
        assert out.loc[0, "dpe_ambigu"] == True            # noqa: E712 — exclu des analyses par étiquette
        # Mêmes étiquettes → pas d'ambiguïté
        dpe["etiquette_dpe"] = ["D", "D"]
        out, _ = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert out.loc[0, "dpe_ambigu"] == False           # noqa: E712

    def test_rapprochement_dpe_sans_candidat(self):
        dpe = pd.DataFrame({
            "type_batiment": ["appartement"], "surface_habitable_logement": [80.0],  # surface trop éloignée
            "latitude": [43.70005], "longitude": [7.26],
            "etiquette_dpe": ["D"], "etiquette_ges": ["D"], "conso_5_usages_par_m2_ep": [200.0],
            "date_etablissement_dpe": pd.to_datetime(["2024-03-01"]),
        })
        out, taux = enrichissement.rapprocher_dpe(self._ventes_geo(), dpe)
        assert pd.isna(out.loc[0, "etiquette_dpe"])
        assert out.loc[0, "dpe_nb_candidats"] == 0 and pd.isna(out.loc[0, "dpe_ambigu"])
        assert taux == 0.0


def _insee_long(geo="06029", niveau="COM", sans=()):
    """Mini fichier INSEE au format long : toutes les mesures pour un territoire."""
    valeurs = {
        "POP": "74350", "SUP": "19.62", "DWELLINGS": "1000", "DWELLINGS_OCS_DW_MAIN": "600",
        "DWELLINGS_OCS_DW_SEC_DW_OCC": "350", "DWELLINGS_OCS_DW_VAC": "50",
        "DWELLINGS_OCS_DW_MAIN_TSH_100": "300", "MED_SL": "24000", "PR_MD60": "22.6",
        "NBEMP_EMPFORM_2": "32120.6", "POP_AGE_Y15T64": "41795", "UNIT_LOC": "4753",
    }
    lignes = [
        {"GEO_OBJECT": niveau, "GEO": geo, "TIME_PERIOD": "2023", "TAB_MEASURE": m, "OBS_VALUE": v}
        for m, v in valeurs.items() if m not in sans
    ]
    # Millésimes antérieurs : ne doivent pas écraser le plus récent
    lignes += [
        {"GEO_OBJECT": niveau, "GEO": geo, "TIME_PERIOD": "2017", "TAB_MEASURE": "POP", "OBS_VALUE": "70000"},
        {"GEO_OBJECT": niveau, "GEO": geo, "TIME_PERIOD": "2012", "TAB_MEASURE": "POP", "OBS_VALUE": "60000"},
        {"GEO_OBJECT": niveau, "GEO": geo, "TIME_PERIOD": "2017", "TAB_MEASURE": "DWELLINGS", "OBS_VALUE": "900"},
    ]
    return lignes


class TestPivotINSEE:
    def test_une_ligne_par_commune_avec_dernier_millesime(self):
        df = pivoter_insee(pd.DataFrame(_insee_long("06029") + _insee_long("06088")))
        assert sorted(df["code_commune"]) == ["06029", "06088"]
        cannes = df[df["code_commune"] == "06029"].iloc[0]
        assert cannes["population"] == 74350      # 2023, pas 2017
        assert cannes["logements"] == 1000        # 2023, pas 2017
        assert cannes["niveau_vie_median"] == 24000
        assert cannes["taux_pauvrete"] == 22.6
        assert set(INSEE_MESURES.values()) <= set(df.columns)

    def test_derivees(self):
        ligne = pivoter_insee(pd.DataFrame(_insee_long())).iloc[0]
        assert ligne["taux_logements_vacants"] == 5.0
        assert ligne["taux_residences_secondaires"] == 35.0
        assert ligne["menages"] == 600
        # Évolution vs recensement PRÉCÉDENT (2017), pas le plus ancien (2012)
        assert ligne["population_ref"] == 70000
        assert ligne["annee_population"] == 2023 and ligne["annee_population_ref"] == 2017
        assert ligne["evolution_population_pct"] == pytest.approx(6.21)

    def test_niveaux_non_communaux_exclus(self):
        lignes = _insee_long("06029") + _insee_long("06", niveau="DEP") + _insee_long("13201", niveau="ARM")
        df = pivoter_insee(pd.DataFrame(lignes))
        assert sorted(df["code_commune"]) == ["06029", "13201"]  # arrondissements gardés, département non

    def test_commune_sans_revenus_garde_des_na(self):
        """Petites communes : Filosofi secrétisé → NaN, pas de ligne perdue."""
        lignes = _insee_long("06029") + [
            l for l in _insee_long("06050") if l["TAB_MEASURE"] not in ("MED_SL", "PR_MD60")]
        df = pivoter_insee(pd.DataFrame(lignes)).set_index("code_commune")
        assert np.isnan(df.loc["06050", "niveau_vie_median"])
        assert df.loc["06050", "population"] == 74350

    def test_mesure_absente_du_fichier_erreur_explicite(self):
        with pytest.raises(ValueError, match="Mesures INSEE absentes"):
            pivoter_insee(pd.DataFrame(_insee_long(sans=("MED_SL",))))

    def test_valeur_vide_au_dernier_millesime_reprend_la_precedente(self):
        """Secret statistique = ligne présente mais OBS_VALUE vide (cas réel Filosofi)."""
        lignes = [l for l in _insee_long() if l["TAB_MEASURE"] != "DWELLINGS" or l["TIME_PERIOD"] != "2023"]
        lignes.append({"GEO_OBJECT": "COM", "GEO": "06029", "TIME_PERIOD": "2023",
                       "TAB_MEASURE": "DWELLINGS", "OBS_VALUE": None})
        lignes = [dict(l, OBS_VALUE=None) if l["TAB_MEASURE"] == "MED_SL" else l for l in lignes]
        ligne = pivoter_insee(pd.DataFrame(lignes)).iloc[0]
        assert ligne["logements"] == 900            # repli sur 2017
        assert np.isnan(ligne["niveau_vie_median"])  # jamais renseigné → NaN, ligne conservée

    def test_commune_en_retard_d_un_millesime_conservee(self):
        """Une commune dont tout s'arrête avant le dernier millésime ne disparaît pas."""
        retard = [dict(l, GEO="06999", TIME_PERIOD="2022") for l in _insee_long() if l["TIME_PERIOD"] == "2023"]
        df = pivoter_insee(pd.DataFrame(_insee_long("06029") + retard)).set_index("code_commune")
        assert df.loc["06999", "population"] == 74350

    def test_doublons_refuses(self):
        lignes = _insee_long("13201") + _insee_long("13201", niveau="ARM")
        with pytest.raises(ValueError, match="doublons"):
            pivoter_insee(pd.DataFrame(lignes))

    def test_population_ref_exige_un_ecart_de_5_ans(self):
        """Une population annuelle N-1 ne doit pas servir de référence."""
        lignes = _insee_long() + [{"GEO_OBJECT": "COM", "GEO": "06029", "TIME_PERIOD": "2022",
                                   "TAB_MEASURE": "POP", "OBS_VALUE": "74000"}]
        ligne = pivoter_insee(pd.DataFrame(lignes)).iloc[0]
        assert ligne["annee_population_ref"] == 2017 and ligne["population_ref"] == 70000
