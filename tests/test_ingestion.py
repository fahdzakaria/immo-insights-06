"""Tests unitaires des modules d'ingestion (hors-ligne : aucun appel réseau)."""

from datetime import date

import pandas as pd
import pytest
import requests

from pipelines import common
from pipelines.ingestion import dpe, dvf, insee, iris, osm
from pipelines.ingestion.run_all import SOURCES


def test_dvf_url():
    assert dvf.dvf_url("06", 2024) == (
        "https://files.data.gouv.fr/geo-dvf/latest/csv/2024/departements/06.csv.gz"
    )


def test_dvf_annees_parametrables(monkeypatch):
    monkeypatch.setenv("DVF_ANNEES", "2023, 2024")
    assert dvf.annees() == [2023, 2024]


def test_dvf_annees_par_defaut_incluent_annee_en_cours(monkeypatch):
    """Sans DVF_ANNEES : de 2021 à l'année en cours (pas de liste figée)."""
    monkeypatch.delenv("DVF_ANNEES", raising=False)
    monkeypatch.delenv("DVF_ANNEE_DEBUT", raising=False)
    annees = dvf.annees()
    assert annees[0] == 2021
    assert annees[-1] == date.today().year
    assert annees == sorted(annees)


def test_insee_schema_long_accepte():
    insee.verifier_schema(["GEO_REF", "GEO_OBJECT", "GEO", "TIME_PERIOD", "DS", "TAB_MEASURE", "OBS_VALUE"])


def test_insee_ancien_format_refuse_avec_message_clair():
    """L'ancien format large (CODGEO, P22_POP…) doit échouer dès l'ingestion."""
    with pytest.raises(ValueError, match="Format INSEE inattendu"):
        insee.verifier_schema(["CODGEO", "P22_POP", "P16_POP"])


class _Reponse:
    status_code = 200

    def raise_for_status(self):
        pass


def test_http_get_retente_une_connexion_coupee_en_lecture(monkeypatch):
    """ChunkedEncodingError (corps tronqué, vu sur l'API ADEME) → on retente."""
    appels = {"n": 0}

    def faux_get(url, **kw):
        appels["n"] += 1
        if appels["n"] < 3:
            raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")
        return _Reponse()

    monkeypatch.setattr(common._session, "get", faux_get)
    monkeypatch.setattr(common.http_get.retry, "sleep", lambda s: None)  # pas d'attente en test
    assert common.http_get("https://exemple.test").status_code == 200
    assert appels["n"] == 3


def test_dpe_rows_from_response():
    page = {
        "total": 2,
        "results": [
            {"numero_dpe": "2606E001", "etiquette_dpe": "C", "code_insee_ban": "06095",
             "_geopoint": "43.6257,6.8866"},
            {"numero_dpe": "2606E002", "etiquette_dpe": "F", "code_insee_ban": "06088",
             "_geopoint": None},  # géolocalisation absente
        ],
    }
    rows = dpe.rows_from_response(page)
    assert len(rows) == 2
    assert rows[0]["latitude"] == 43.6257 and rows[0]["longitude"] == 6.8866
    assert rows[1]["latitude"] is None
    assert rows[0]["code_insee_ban"] == "06095"
    assert "_geopoint" not in rows[0]


def test_osm_build_query_contient_departement_et_filtres():
    q = osm.build_query("06")
    assert 'ISO3166-2"="FR-06"' in q
    assert "school" in q and "station" in q and "supermarket" in q
    assert "out center" in q


def test_osm_elements_to_rows():
    elements = [
        # node classique
        {"type": "node", "id": 1, "lat": 43.7, "lon": 7.2,
         "tags": {"amenity": "school", "name": "École Jean Moulin"}},
        # way avec centroïde (bâtiment)
        {"type": "way", "id": 2, "center": {"lat": 43.6, "lon": 7.1},
         "tags": {"shop": "supermarket"}},
        # élément sans coordonnées → ignoré
        {"type": "relation", "id": 3, "tags": {"railway": "station"}},
    ]
    rows = osm.elements_to_rows(elements)
    assert len(rows) == 2
    assert rows[0]["categorie"] == "education"
    assert rows[0]["nom"] == "École Jean Moulin"
    assert rows[1]["categorie"] == "commerce"
    assert rows[1]["latitude"] == 43.6


def test_osm_categorize_ignore_tags_hors_perimetre():
    assert osm.categorize({"shop": "clothes"}) is None
    assert osm.categorize({"railway": "tram_stop"}) == "transport"


def test_registre_des_sources_complet():
    assert set(SOURCES) == {"dvf", "insee", "loyers", "dpe", "osm", "iris"}


def test_dpe_telechargement_partiel_refuse():
    with pytest.raises(ValueError, match="incomplet"):
        dpe.verifier_complet(30_000, 305_138, "06")


def test_dpe_telechargement_complet_accepte():
    dpe.verifier_complet(305_138, 305_138, "06")
    dpe.verifier_complet(304_000, 305_138, "06")   # DPE ajoutés pendant la pagination : toléré
    dpe.verifier_complet(10, None, "06")           # total non annoncé : pas de contrôle


def test_dvf_annee_non_publiee_ignoree(monkeypatch, tmp_path):
    """Une année en 404 (pas encore publiée par Etalab) ne fait pas échouer l'ingestion."""
    monkeypatch.setenv("DVF_ANNEES", "2099")
    monkeypatch.setattr(dvf, "BRONZE_DIR", tmp_path)

    def faux_download(url, **kw):
        reponse = requests.Response()
        reponse.status_code = 404
        raise requests.HTTPError(response=reponse)

    monkeypatch.setattr(dvf, "download_bytes", faux_download)
    assert dvf.ingest(["06"]) == []
    assert not list(tmp_path.rglob("*.parquet"))


# --- Contours IRIS (quartiers) ---

def _feature_iris(code="060880401", **props):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[7.29, 43.69], [7.30, 43.69], [7.30, 43.70], [7.29, 43.69]]]},
        "properties": {"cleabs": "IRIS____1", "code_insee": code[:5], "nom_commune": "Nice",
                       "iris": code[5:], "code_iris": code, "nom_iris": "Mont Boron", "type_iris": "H", **props},
    }


class _ReponseJson:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_iris_build_params_filtre_le_departement_et_trie():
    p = iris.build_params("06", start_index=1000)
    assert p["CQL_FILTER"] == "code_insee LIKE '06%'"
    assert p["SORTBY"] == "code_iris"  # pagination stable
    assert p["SRSNAME"] == "EPSG:4326" and p["STARTINDEX"] == 1000


def test_iris_features_to_rows():
    rows = iris.features_to_rows([_feature_iris()])
    assert rows[0]["code_iris"] == "060880401" and rows[0]["code_commune"] == "06088"
    assert rows[0]["nom_iris"] == "Mont Boron" and rows[0]["type_iris"] == "H"
    assert '"type":"Polygon"' in rows[0]["geometrie_geojson"]


def test_iris_schema_change_refuse_avec_message_clair():
    f = _feature_iris()
    del f["properties"]["code_iris"]
    with pytest.raises(ValueError, match="Format IRIS inattendu"):
        iris.features_to_rows([f])


def test_iris_geometrie_absente_refusee():
    f = _feature_iris()
    f["geometry"] = None
    with pytest.raises(ValueError, match="géométrie"):
        iris.features_to_rows([f])


def test_iris_telecharger_pagine_jusqu_au_bout(monkeypatch):
    monkeypatch.setattr(iris, "TAILLE_PAGE", 2)
    codes = ["060880101", "060880102", "060880103"]
    appels = []

    def faux_get(url, params=None, **kw):
        appels.append(params["STARTINDEX"])
        page = codes[params["STARTINDEX"]:params["STARTINDEX"] + 2]
        return _ReponseJson({"numberMatched": 3, "features": [_feature_iris(c) for c in page]})

    monkeypatch.setattr(iris, "http_get", faux_get)
    rows = iris.telecharger("06")
    assert [r["code_iris"] for r in rows] == codes
    assert appels == [0, 2]


def test_iris_telechargement_incomplet_refuse(monkeypatch):
    """Le WFS annonce 500 contours mais n'en renvoie qu'un : on n'écrit pas un bronze tronqué."""
    monkeypatch.setattr(iris, "http_get", lambda url, params=None, **kw: _ReponseJson(
        {"numberMatched": 500, "features": [_feature_iris()]}))
    with pytest.raises(ValueError, match="1 contours reçus pour 500"):
        iris.telecharger("06")


def test_iris_reponse_vide_refusee(monkeypatch):
    monkeypatch.setattr(iris, "http_get", lambda url, params=None, **kw: _ReponseJson(
        {"numberMatched": 0, "features": []}))
    with pytest.raises(ValueError, match="aucun contour"):
        iris.telecharger("06")


def test_iris_ingest_idempotent(monkeypatch, tmp_path):
    """Deuxième appel : manifeste présent → aucun téléchargement."""
    monkeypatch.setattr(iris, "BRONZE_DIR", tmp_path)
    appels = {"n": 0}

    def faux_get(url, params=None, **kw):
        appels["n"] += 1
        return _ReponseJson({"numberMatched": 1, "features": [_feature_iris()]})

    monkeypatch.setattr(iris, "http_get", faux_get)
    (chemin,) = iris.ingest(["06"])
    assert pd.read_parquet(chemin)["code_iris"].tolist() == ["060880401"]
    assert "Licence Ouverte" in chemin.with_suffix(".manifest.json").read_text()
    iris.ingest(["06"])
    assert appels["n"] == 1
    iris.ingest(["06"], force=True)
    assert appels["n"] == 2


def test_overpass_reponse_partielle_refusee():
    """Overpass répond 200 même quand il coupe la requête : le champ remark le trahit."""
    with pytest.raises(ValueError, match="incomplète"):
        osm.verifier_reponse({"elements": [{"id": 1}], "remark": "runtime error: Query timed out"}, "06")
    with pytest.raises(ValueError, match="vide"):
        osm.verifier_reponse({"elements": []}, "06")
    assert osm.verifier_reponse({"elements": [{"id": 1}]}, "06") == [{"id": 1}]


def test_ban_retente_un_429(monkeypatch):
    """Un 429 passager de la BAN est retenté au lieu de faire échouer le silver."""
    from pipelines.silver import geocodage

    class Rep:
        def __init__(self, statut):
            self.status_code = statut
            self.content = b"adresse,code_postal,latitude,longitude,result_score\n1 rue x,06000,43.7,7.26,0.9\n"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    appels = {"n": 0}

    def faux_post(*a, **kw):
        appels["n"] += 1
        return Rep(429 if appels["n"] < 3 else 200)

    monkeypatch.setattr(geocodage._session, "post", faux_post)
    monkeypatch.setattr(geocodage._appeler_ban.retry, "sleep", lambda s: None)
    lot = pd.DataFrame({"adresse": ["1 rue x"], "code_postal": ["06000"]})
    assert len(geocodage._appeler_ban(lot)) == 1
    assert appels["n"] == 3


class _ReponseOverpass:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_osm_bascule_sur_un_miroir_quand_la_principale_tombe(monkeypatch):
    appels = []

    def faux_get(url, **kwargs):
        appels.append(url)
        if url == osm.OVERPASS_URL:
            raise requests.ConnectionError("Network is unreachable")
        return _ReponseOverpass({"elements": [{"id": 1}]})

    monkeypatch.setattr(osm, "http_get", faux_get)
    elements, url = osm.interroger_overpass("q", "06")
    assert elements == [{"id": 1}]
    assert url == osm.OVERPASS_MIROIRS[1]
    assert appels == osm.OVERPASS_MIROIRS[:2]


def test_osm_toutes_instances_en_panne_leve_une_erreur_claire(monkeypatch):
    def faux_get(url, **kwargs):
        raise common.RetryableHTTPError("HTTP 502")

    monkeypatch.setattr(osm, "http_get", faux_get)
    with pytest.raises(osm.OverpassIndisponible, match="Aucune instance Overpass"):
        osm.interroger_overpass("q", "06")


def test_osm_garde_le_bronze_existant_si_overpass_est_en_panne(monkeypatch, tmp_path):
    monkeypatch.setattr(osm, "BRONZE_DIR", tmp_path)
    ancien = tmp_path / "osm" / "departement=06" / "pois.parquet"
    ancien.parent.mkdir(parents=True)
    pd.DataFrame({"id": [1]}).to_parquet(ancien)
    monkeypatch.setattr(osm, "already_ingested", lambda *a, **k: False)   # bronze « trop vieux »

    def panne(query, dep):
        raise osm.OverpassIndisponible("panne")

    monkeypatch.setattr(osm, "interroger_overpass", panne)
    assert osm.ingest(["06"]) == [ancien]


def test_osm_sans_bronze_existant_la_panne_remonte(monkeypatch, tmp_path):
    monkeypatch.setattr(osm, "BRONZE_DIR", tmp_path)
    monkeypatch.setattr(osm, "already_ingested", lambda *a, **k: False)

    def panne(query, dep):
        raise osm.OverpassIndisponible("panne")

    monkeypatch.setattr(osm, "interroger_overpass", panne)
    with pytest.raises(osm.OverpassIndisponible):
        osm.ingest(["06"])

