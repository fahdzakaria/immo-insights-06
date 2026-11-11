"""Tests unitaires des modules d'ingestion (hors-ligne : aucun appel réseau)."""

from datetime import date

import pandas as pd
import pytest
import requests

from pipelines import common
from pipelines.ingestion import dpe, dvf, insee, osm
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
    assert set(SOURCES) == {"dvf", "insee", "loyers", "dpe", "osm"}


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
