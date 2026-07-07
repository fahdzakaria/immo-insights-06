"""Tests unitaires des modules d'ingestion (hors-ligne : aucun appel réseau)."""

import pandas as pd

from pipelines.ingestion import dpe, dvf, osm
from pipelines.ingestion.run_all import SOURCES


def test_dvf_url():
    assert dvf.dvf_url("06", 2024) == (
        "https://files.data.gouv.fr/geo-dvf/latest/csv/2024/departements/06.csv.gz"
    )


def test_dvf_annees_parametrables(monkeypatch):
    monkeypatch.setenv("DVF_ANNEES", "2023, 2024")
    assert dvf.annees() == [2023, 2024]


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
