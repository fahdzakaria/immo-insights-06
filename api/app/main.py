"""API Immo Data Platform — sert les data marts gold au frontend.

Architecture : DuckDB en mémoire + vues sur les Parquet gold (voir db.py).
Filtrage 100 % côté base (requêtes paramétrées), marts pré-agrégés,
cache TTL 10 min : aucune réponse ne dépasse quelques millisecondes.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.routers import communes, investissement, marche, tendances

app = FastAPI(
    title="Immo Data Platform API",
    description=(
        "Analyse du marché immobilier français à partir de données publiques "
        "(DVF, INSEE, DPE ADEME, carte des loyers, OpenStreetMap). "
        "Pipeline : Airflow → medallion Parquet → dbt → DuckDB."
    ),
    version="1.0.0",
    contact={"name": "Zakaria Fahd"},
)

# API publique en lecture seule : CORS ouvert
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(marche.router)
app.include_router(communes.router)
app.include_router(tendances.router)
app.include_router(investissement.router)


@app.get("/", tags=["système"])
def root() -> dict:
    return {"service": "immo-data-platform-api", "docs": "/docs", "version": "1.0.0"}


@app.get("/health", tags=["système"])
def health() -> dict:
    """Statut : présence des marts gold + warehouse requêtable."""
    marts = db.marts_disponibles()
    statut = "ok" if len(marts) == len(db.MARTS) else "degraded"
    return {"status": statut, "marts_disponibles": marts,
            "gold_dir": str(db.gold_dir()),
            "warehouse_exists": Path(os.environ.get("DUCKDB_PATH", "/data/warehouse/immo.duckdb")).exists()}
