"""Socle commun des pipelines d'ingestion.

Garanties apportées à tous les modules :
- HTTP avec retry exponentiel (les APIs publiques tombent régulièrement) ;
- écritures Parquet ATOMIQUES (tmp + rename : jamais de fichier à moitié écrit) ;
- idempotence via un manifeste JSON posé à côté de chaque Parquet :
  rejouer l'ingestion ne re-télécharge pas une source déjà présente,
  sauf si --force est passé.
"""

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger("ingestion")

# UA identifiable : demandé par la charte d'usage de la BAN et d'Overpass
USER_AGENT = "immo-data-platform/0.1 (projet portfolio data engineering)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class RetryableHTTPError(Exception):
    """Erreur HTTP transitoire (5xx, 429) : on retente."""


@retry(
    # ChunkedEncodingError = connexion coupée EN COURS de lecture du corps (vu sur
    # l'API ADEME) : ce n'est pas une sous-classe de ConnectionError.
    retry=retry_if_exception_type((
        RetryableHTTPError, requests.ConnectionError, requests.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    reraise=True,
)
def http_get(url: str, *, params: dict | None = None, timeout: int = 300, **kwargs) -> requests.Response:
    """GET avec retry sur les erreurs transitoires. 4xx (hors 429) remonte direct."""
    resp = _session.get(url, params=params, timeout=timeout, **kwargs)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise RetryableHTTPError(f"HTTP {resp.status_code} sur {url}")
    resp.raise_for_status()
    return resp


def download_bytes(url: str, *, params: dict | None = None) -> bytes:
    """Télécharge un fichier en mémoire (les sources ici font < 200 Mo)."""
    resp = http_get(url, params=params)
    logger.info("Téléchargé %s (%.1f Mo)", url, len(resp.content) / 1e6)
    return resp.content


def read_csv_flexible(payload: bytes, **kwargs) -> pd.DataFrame:
    """Lit un CSV dont le séparateur (';' ou ',') et l'encodage varient selon la source."""
    for encoding in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(payload), sep=";", encoding=encoding, **kwargs)
            if df.shape[1] == 1:  # mauvais séparateur → tout dans une colonne
                df = pd.read_csv(io.BytesIO(payload), sep=",", encoding=encoding, **kwargs)
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV illisible en utf-8 comme en latin-1")


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Écrit un Parquet de façon atomique (tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return path


def _manifest_path(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(".manifest.json")


def write_manifest(parquet_path: Path, *, source: str, rows: int, extra: dict | None = None) -> None:
    """Trace la provenance d'un Parquet bronze (source, date, volumétrie)."""
    manifest = {
        "source": source,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        **(extra or {}),
    }
    _manifest_path(parquet_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def already_ingested(
    parquet_path: Path,
    *,
    source: str,
    force: bool = False,
    max_age_jours: float | None = None,
) -> bool:
    """True si ce Parquet a déjà été produit depuis la même source (et pas de --force).

    C'est la clé de l'idempotence : même source + fichier présent = on ne refait rien.

    `max_age_jours` est la POLITIQUE DE FRAÎCHEUR : les sources publiques sont
    republiées sous des URLs stables (DVF "latest", API ADEME…), donc sans
    limite d'âge le bronze resterait figé au premier téléchargement. Au-delà
    de cet âge, on re-télécharge même si la source n'a pas changé d'URL.
    """
    if force or not parquet_path.exists():
        return False
    mpath = _manifest_path(parquet_path)
    if not mpath.exists():
        return False
    try:
        manifest = json.loads(mpath.read_text())
    except json.JSONDecodeError:
        return False
    if manifest.get("source") != source:
        return False
    if max_age_jours is not None:
        try:
            ingere_le = datetime.fromisoformat(manifest["ingested_at"])
        except (KeyError, ValueError):
            return False
        age = datetime.now(timezone.utc) - ingere_le
        if age.total_seconds() > max_age_jours * 86_400:
            logger.info("Ingestion périmée (%.1f j > %s j), on rafraîchit : %s",
                        age.total_seconds() / 86_400, max_age_jours, parquet_path)
            return False
    logger.info("Déjà ingéré, on saute : %s", parquet_path)
    return True
