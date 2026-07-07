"""Configuration partagée des pipelines : chemins du data lake, départements.

Tout est surchargeable par variables d'environnement (voir docker-compose.yml),
avec des valeurs par défaut qui fonctionnent aussi hors Docker.
"""

import os
from pathlib import Path

# Racine du data lake (montée sur /data dans les conteneurs)
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))

# Architecture medallion
BRONZE_DIR = DATA_DIR / "bronze"    # données brutes telles que téléchargées
SILVER_DIR = DATA_DIR / "silver"    # nettoyées, géocodées, enrichies
GOLD_DIR = DATA_DIR / "gold"        # exports éventuels des marts

# Data warehouse DuckDB (écrit par dbt, lu en read-only par l'API)
DUCKDB_PATH = Path(os.environ.get("DUCKDB_PATH", DATA_DIR / "warehouse" / "immo.duckdb"))


def departements() -> list[str]:
    """Départements ciblés par le pipeline, ex: DEPARTEMENTS="06,83,13".

    On démarre sur les Alpes-Maritimes (06) pour valider tout le flux.
    """
    raw = os.environ.get("DEPARTEMENTS", "06")
    return [d.strip() for d in raw.split(",") if d.strip()]
