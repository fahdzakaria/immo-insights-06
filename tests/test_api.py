"""Tests de l'API FastAPI sur des marts gold synthétiques (hors-ligne).

Le fixture construit un mini data lake gold dans un tmpdir, pointe GOLD_DIR
dessus et réinitialise la connexion DuckDB de l'API.
"""

import sys

import pandas as pd
import pytest

sys.path.insert(0, "/opt/airflow/api")  # le code de l'API est monté là (docker-compose)

fastapi = pytest.importorskip("fastapi", reason="fastapi requis (lancer dans le conteneur)")

from fastapi.testclient import TestClient  # noqa: E402


def _gold_fixture(tmp_path):
    """Deux communes × appartement, données minimales mais réalistes."""
    pd.DataFrame({
        "commune_type_id": ["06088_appartement", "06029_appartement"],
        "code_commune": ["06088", "06029"], "nom_commune": ["Nice", "Cannes"],
        "code_departement": ["06", "06"], "type_bien": ["appartement"] * 2,
        "nb_ventes_total": [1000, 400], "nb_ventes_24m": [400, 150],
        "prix_m2_median": [4600.0, 5400.0], "prix_m2_p25": [3800.0, 4500.0],
        "prix_m2_p75": [5600.0, 6600.0], "prix_median": [250000.0, 300000.0],
        "surface_mediane": [52.0, 55.0], "evolution_1an_pct": [1.5, -0.5],
        "evolution_3ans_pct": [8.0, 5.0], "latitude": [43.7, 43.55], "longitude": [7.26, 7.02],
        "population": [353701, 74040], "niveau_vie_median": [22000.0, 23500.0],
        "taux_pauvrete": [18.0, 15.0],
    }).to_parquet(tmp_path / "mart_prix_m2_par_commune.parquet")

    pd.DataFrame({
        "evolution_id": ["06_2024Q1_appartement", "06088_2024Q1_appartement"],
        "maille": ["departement", "commune"], "code_departement": ["06", "06"],
        "code_commune": [None, "06088"], "nom_commune": [None, "Nice"],
        "type_bien": ["appartement"] * 2, "trimestre": ["2024Q1"] * 2, "annee": [2024] * 2,
        "nb_ventes": [5000, 900], "prix_m2_median": [4700.0, 4600.0],
        "prix_median": [260000.0, 250000.0], "surface_mediane": [52.0, 51.0],
    }).to_parquet(tmp_path / "mart_evolution_trimestrielle.parquet")

    pd.DataFrame({
        "commune_type_id": ["06088_appartement", "06029_appartement"],
        "code_commune": ["06088", "06029"], "nom_commune": ["Nice", "Cannes"],
        "code_departement": ["06", "06"], "type_bien": ["appartement"] * 2,
        "nb_ventes_24m": [400, 150], "prix_m2_median": [4600.0, 5400.0],
        "loyer_m2": [20.5, 20.4], "loyer_fiabilite": ["commune"] * 2,
        "rendement_brut_pct": [5.35, 4.53],
    }).to_parquet(tmp_path / "mart_rendement_locatif.parquet")

    pd.DataFrame({
        "impact_id": ["06_appartement_C", "06_appartement_G"],
        "code_departement": ["06", "06"], "type_bien": ["appartement"] * 2,
        "etiquette_dpe": ["C", "G"], "nb_ventes": [15000, 500],
        "prix_m2_median": [4700.0, 4400.0], "ecart_vs_marche_pct": [0.7, -2.0],
        "conso_ep_m2_mediane": [120.0, 450.0],
    }).to_parquet(tmp_path / "mart_impact_dpe.parquet")

    pd.DataFrame({
        "commune_type_id": ["06088_appartement"], "code_commune": ["06088"],
        "nom_commune": ["Nice"], "code_departement": ["06"], "type_bien": ["appartement"],
        "nb_ventes_24m": [400], "prix_m2_median": [4600.0], "rendement_brut_pct": [5.35],
        "evolution_3ans_pct": [8.0], "evolution_population_pct": [1.2],
        "taux_logements_vacants": [8.5], "pois_moyens_500m": [12.3],
        "score_prix": [40.0], "score_rendement": [60.0], "score_dynamique_marche": [70.0],
        "score_dynamique_demo": [55.0], "score_services": [80.0], "score_tension": [45.0],
        "score_investissement": [59.0],
    }).to_parquet(tmp_path / "mart_score_investissement.parquet")


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module=None):
    tmp = tmp_path_factory.mktemp("gold")
    _gold_fixture(tmp)
    import os
    os.environ["GOLD_DIR"] = str(tmp)
    from app import cache, db
    db.reset()
    cache.vider()
    from app.main import app
    return TestClient(app)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert len(body["marts_disponibles"]) == 5


def test_communes_filtre_prix(client):
    r = client.get("/api/v1/communes", params={"departement": "06", "prix_m2_max": 5000})
    body = r.json()
    assert body["total"] == 1
    assert body["resultats"][0]["nom_commune"] == "Nice"


def test_communes_recherche_et_tri(client):
    r = client.get("/api/v1/communes", params={"recherche": "cann", "tri": "prix_m2", "ordre": "desc"})
    assert [c["nom_commune"] for c in r.json()["resultats"]] == ["Cannes"]


def test_communes_tri_invalide_rejete(client):
    r = client.get("/api/v1/communes", params={"tri": "valeur_fonciere; DROP TABLE x"})
    assert r.status_code == 422, "le tri hors liste blanche doit être rejeté"


def test_detail_commune_et_404(client):
    ok = client.get("/api/v1/communes/06088").json()
    assert ok["nom_commune"] == "Nice"
    assert ok["scores"][0]["score_investissement"] == 59.0
    assert client.get("/api/v1/communes/99999").status_code == 404


def test_tendances_mailles(client):
    dep = client.get("/api/v1/tendances", params={"departement": "06"}).json()
    assert dep["maille"] == "departement" and len(dep["resultats"]) == 1
    com = client.get("/api/v1/tendances", params={"code_commune": "06088"}).json()
    assert com["maille"] == "commune" and com["resultats"][0]["nb_ventes"] == 900


def test_rendement_filtre(client):
    r = client.get("/api/v1/rendement", params={"rendement_min": 5}).json()
    assert r["total"] == 1
    assert r["resultats"][0]["code_commune"] == "06088"


def test_opportunites(client):
    r = client.get("/api/v1/opportunites", params={"score_min": 50}).json()
    assert r["resultats"][0]["score_investissement"] == 59.0


def test_estimation_avec_ajustement_dpe(client):
    r = client.get("/api/v1/estimation", params={
        "code_commune": "06088", "type_bien": "appartement",
        "surface": 50, "etiquette_dpe": "G"})
    body = r.json()
    # 50 m² × 4600 €/m² × (1 - 2 %) = 225 400 €
    assert body["prix_estime"] == 225400
    assert body["ajustement_dpe_pct"] == -2.0
    assert body["fourchette_basse"] < body["prix_estime"] < body["fourchette_haute"]


def test_estimation_commune_inconnue(client):
    r = client.get("/api/v1/estimation", params={"code_commune": "99999", "surface": 50})
    assert r.status_code == 404


def test_kpis(client):
    body = client.get("/api/v1/kpis", params={"departement": "06"}).json()
    assert body["nb_ventes_total"] == 5000
    assert body["rendement_brut_median"] == pytest.approx(4.94)
