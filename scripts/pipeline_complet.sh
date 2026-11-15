#!/usr/bin/env bash
# Pipeline complet SANS Airflow : bronze → silver → marts dbt (+ tests) → export
# JSON du site. C'est ce que lance la publication automatique (GitHub Actions),
# à partir d'un data lake vide. À exécuter dans l'image Airflow du projet, avec
# le dépôt monté sur /opt/airflow (voir .github/workflows/publication.yml).
#
# Variables attendues : DATA_DIR, DUCKDB_PATH, GOLD_DIR, FRONT_DATA_DIR.
# S'arrête à la première erreur : si une source est indisponible ou si un test
# dbt échoue, rien n'est exporté et l'ancien site reste en ligne.
set -euo pipefail

cd /opt/airflow
mkdir -p "$DATA_DIR/warehouse" "$GOLD_DIR"

echo "::group::Bronze — ingestion des sources publiques"
python -m pipelines.ingestion.run_all
echo "::endgroup::"

echo "::group::Silver — nettoyage, géocodage, enrichissement"
python -m pipelines.silver.run_all
echo "::endgroup::"

echo "::group::Gold — marts dbt et tests qualité"
(cd dbt/immo && dbt build --profiles-dir . --no-partial-parse)
echo "::endgroup::"

echo "::group::Export JSON pour le site"
python -m pipelines.export_front
echo "::endgroup::"
