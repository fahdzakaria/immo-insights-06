"""DAG principal : pipeline immobilier de bout en bout.

    bronze (5 sources en parallèle)
      → silver (nettoyages en parallèle → enrichissement)
        → dbt run → dbt test → dbt docs + export JSON pour le front

Idempotence : le bronze saute les sources déjà ingérées (manifestes) ; le
silver et dbt recalculent tout (déterministes). Relancer le DAG est donc
toujours sans danger.

Alerte : chaque échec définitif de tâche appelle `alerte_echec` — log ERROR +
webhook Slack/Discord (ALERT_WEBHOOK_URL) et/ou Telegram (TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID). Voir pipelines/alertes.py.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from functools import partial

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

from pipelines import alertes, config, export_front
from pipelines.ingestion import dpe, dvf, insee, loyers, osm
from pipelines.silver import dpe_clean, dvf_clean, enrichissement, osm_clean, referentiels

logger = logging.getLogger("immo_pipeline")

DBT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt/immo")
DBT_CMD = f"cd {DBT_DIR} && dbt {{}} --profiles-dir ."


def alerte_echec(context) -> None:
    """Callback d'échec définitif d'une tâche : log + webhook et/ou Telegram (pipelines.alertes)."""
    ti = context["task_instance"]
    alertes.envoyer_alerte(
        f"❌ Pipeline immo : échec de {ti.task_id} "
        f"(run {context['run_id']}, tentative {ti.try_number})\n"
        f"Log : {ti.log_url}"
    )


default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "on_failure_callback": alerte_echec,
    # Les tâches communiquent par le data lake, pas par XCom — et les
    # fonctions retournent des Path non sérialisables en JSON.
    "do_xcom_push": False,
}

with DAG(
    dag_id="immo_pipeline",
    description="DVF/INSEE/DPE/loyers/OSM → bronze → silver → marts dbt",
    schedule="0 6 * * *",  # tous les jours à 6h (les sources bougent au fil de l'eau)
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    catchup=False,  # pas de rattrapage : chaque run reconstruit l'état courant
    max_active_runs=1,  # un seul écrivain sur le warehouse DuckDB
    default_args=default_args,
    doc_md=__doc__,
    tags=["immo", "medallion", "dbt"],
) as dag:
    departements = config.departements()

    with TaskGroup(group_id="bronze", tooltip="Ingestion des 5 sources (idempotente)") as bronze:
        b_dvf = PythonOperator(task_id="dvf", python_callable=partial(dvf.ingest, departements))
        b_insee = PythonOperator(task_id="insee", python_callable=partial(insee.ingest, departements))
        b_loyers = PythonOperator(task_id="loyers", python_callable=partial(loyers.ingest, departements))
        b_dpe = PythonOperator(task_id="dpe", python_callable=partial(dpe.ingest, departements))
        b_osm = PythonOperator(task_id="osm", python_callable=partial(osm.ingest, departements))

    with TaskGroup(group_id="silver", tooltip="Nettoyage + enrichissement") as silver:
        s_referentiels = PythonOperator(
            task_id="referentiels", python_callable=partial(referentiels.build, departements))
        s_dpe = PythonOperator(task_id="dpe", python_callable=partial(dpe_clean.build, departements))
        s_osm = PythonOperator(task_id="osm", python_callable=partial(osm_clean.build, departements))
        s_dvf = PythonOperator(task_id="dvf", python_callable=partial(dvf_clean.build, departements))
        s_enrichissement = PythonOperator(
            task_id="enrichissement", python_callable=partial(enrichissement.build, departements))
        [s_referentiels, s_dpe, s_osm, s_dvf] >> s_enrichissement

    # Dépendances fines bronze → silver : chaque nettoyage n'attend que SA source
    b_dvf >> s_dvf
    b_dpe >> s_dpe
    b_osm >> s_osm
    [b_insee, b_loyers] >> s_referentiels

    dbt_run = BashOperator(task_id="dbt_run", bash_command=DBT_CMD.format("run"))
    dbt_test = BashOperator(task_id="dbt_test", bash_command=DBT_CMD.format("test"))
    dbt_docs = BashOperator(task_id="dbt_docs", bash_command=DBT_CMD.format("docs generate"))

    # Marts validés par dbt test → JSON embarqués par le site (frontend/public/data).
    # Publier en ligne = redéployer le front (voir docs/deploiement.md).
    export_json_front = PythonOperator(task_id="export_json_front", python_callable=export_front.exporter)

    silver >> dbt_run >> dbt_test >> [dbt_docs, export_json_front]
