# Image Airflow + dépendances data (pandas, duckdb, dbt-duckdb).
# Python 3.11 imposé par la stack du projet.
FROM apache/airflow:2.10.5-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
