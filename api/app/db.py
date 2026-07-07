"""Accès données : DuckDB EN MÉMOIRE + vues sur les Parquet gold.

Pourquoi pas le fichier warehouse immo.duckdb ? DuckDB n'accepte qu'un seul
écrivain : le DAG Airflow verrouille le fichier pendant dbt run. En lisant
les Parquet gold via des vues, l'API :
 - ne pose AUCUN verrou sur le warehouse ;
 - voit automatiquement les marts rafraîchis (les fichiers sont remplacés
   atomiquement par dbt) ;
 - reste rapide : les marts sont pré-agrégés (quelques centaines de lignes),
   DuckDB scanne du Parquet en microsecondes.

Toutes les requêtes sont PARAMÉTRÉES (placeholders ?) — jamais de valeur
utilisateur interpolée dans le SQL.
"""

import logging
import os
import threading
from pathlib import Path

import duckdb

logger = logging.getLogger("api.db")

MARTS = [
    "mart_prix_m2_par_commune",
    "mart_evolution_trimestrielle",
    "mart_rendement_locatif",
    "mart_impact_dpe",
    "mart_score_investissement",
]

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None


def gold_dir() -> Path:
    return Path(os.environ.get("GOLD_DIR", "/data/gold"))


def marts_disponibles() -> list[str]:
    return [m for m in MARTS if (gold_dir() / f"{m}.parquet").exists()]


def _init_conn() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    for mart in MARTS:
        path = gold_dir() / f"{mart}.parquet"
        # La vue référence le chemin : chaque requête lit le fichier courant
        con.execute(f"CREATE OR REPLACE VIEW {mart} AS SELECT * FROM read_parquet('{path}')")
    logger.info("Connexion DuckDB initialisée sur %s (%d marts)", gold_dir(), len(MARTS))
    return con


def reset() -> None:
    """Réinitialise la connexion (utilisé par les tests pour changer GOLD_DIR)."""
    global _conn
    with _lock:
        _conn = None


def query(sql: str, params: list | None = None) -> list[dict]:
    """Exécute une requête paramétrée et retourne des lignes dict (JSON-ready)."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = _init_conn()
        cur = _conn.execute(sql, params or [])
        colonnes = [d[0] for d in cur.description]
        return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


def query_one(sql: str, params: list | None = None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None
