"""Tests d'intégrité des DAGs Airflow : import sans erreur, structure attendue.

Ces tests s'exécutent dans le conteneur (Airflow installé) :
    docker compose exec airflow-scheduler bash -c "cd /opt/airflow && python -m pytest tests/"
"""

import pytest

airflow = pytest.importorskip("airflow", reason="Airflow requis (lancer dans le conteneur)")

from airflow.models import DagBag  # noqa: E402


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder="/opt/airflow/dags", include_examples=False)


def test_aucune_erreur_d_import(dagbag):
    assert dagbag.import_errors == {}, f"Erreurs d'import DAG : {dagbag.import_errors}"


@pytest.fixture(scope="module")
def dag(dagbag):
    dag = dagbag.get_dag("immo_pipeline")
    assert dag is not None
    return dag


def test_structure_du_dag(dag):
    ids = set(dag.task_ids)
    attendus = {
        "bronze.dvf", "bronze.insee", "bronze.loyers", "bronze.dpe", "bronze.osm",
        "silver.referentiels", "silver.dpe", "silver.osm", "silver.dvf", "silver.enrichissement",
        "dbt_run", "dbt_test", "dbt_docs",
    }
    assert ids == attendus


def test_dependances_critiques(dag):
    # L'enrichissement attend tous les nettoyages silver
    enrich = dag.get_task("silver.enrichissement")
    amont = set(enrich.upstream_task_ids)
    assert {"silver.referentiels", "silver.dpe", "silver.osm", "silver.dvf"} <= amont
    # dbt s'exécute après le silver, tests après run
    assert "dbt_run" in dag.get_task("dbt_test").upstream_task_ids
    assert "silver.enrichissement" in dag.get_task("dbt_run").upstream_task_ids


def test_garde_fous_operationnels(dag):
    assert dag.default_args["retries"] >= 1, "un retry minimum est exigé"
    assert dag.default_args["on_failure_callback"] is not None, "alerte d'échec obligatoire"
    assert dag.max_active_runs == 1, "DuckDB n'accepte qu'un écrivain"
    assert not dag.catchup
