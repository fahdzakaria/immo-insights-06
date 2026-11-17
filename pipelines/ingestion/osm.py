"""Ingestion des points d'intérêt OpenStreetMap (API Overpass) → bronze.

Trois catégories utiles au score d'investissement :
- education : écoles, crèches, collèges/lycées, universités
- transport : gares, arrêts de tram, arrêts de bus
- commerce  : supermarchés, supérettes, boulangeries, centres commerciaux, marchés

On interroge nodes + ways + relations (`nwr`) avec `out center` : les
bâtiments dessinés en polygone ressortent avec leur centroïde.

Sortie : data/bronze/osm/departement={dep}/pois.parquet
"""

import json
import logging
import re
from pathlib import Path

import pandas as pd
import requests
from tenacity import stop_after_attempt

from pipelines.common import RetryableHTTPError, already_ingested, atomic_write_parquet, http_get, write_manifest
from pipelines.config import BRONZE_DIR

logger = logging.getLogger("ingestion.osm")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Instances publiques de la même API Overpass, essayées dans l'ordre quand la
# principale est en panne (vu le 2026-11-17 : « Network is unreachable » puis 502).
OVERPASS_MIROIRS = [
    OVERPASS_URL,
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
# Connexion courte (un miroir injoignable est vite écarté), lecture longue (la
# requête du département prend parfois plus d'une minute côté serveur).
DELAIS_OVERPASS = (15, 200)   # la requête demande au serveur d'abandonner à 180 s
# 2 essais par instance au lieu de 5 : trois instances bloquées tiennent ainsi
# dans ~20 min, sous le timeout de 45 min du job de publication.
_get_overpass = http_get.retry_with(stop=stop_after_attempt(2))


class OverpassIndisponible(RuntimeError):
    """Aucune instance Overpass n'a renvoyé de réponse exploitable."""

# OSM évolue en continu : rafraîchissement hebdomadaire
FRAICHEUR_JOURS = 6   # < 7 : le cron du lundi retrouve un bronze « périmé » et le rafraîchit chaque semaine

# (catégorie, clé OSM, regex de valeurs)
POI_FILTERS = [
    ("education", "amenity", "^(school|kindergarten|college|university)$"),
    ("transport", "railway", "^(station|tram_stop)$"),
    ("transport", "highway", "^(bus_stop)$"),
    ("commerce", "shop", "^(supermarket|convenience|bakery|mall|department_store)$"),
    ("commerce", "amenity", "^(marketplace)$"),
]


def build_query(dep: str) -> str:
    """Requête Overpass QL : tous les POI ciblés dans le département (zone ISO)."""
    clauses = "\n".join(
        f'  nwr["{key}"~"{regex}"](area.dep);' for _, key, regex in POI_FILTERS
    )
    return (
        '[out:json][timeout:180];\n'
        f'area["ISO3166-2"="FR-{dep}"][admin_level=6]->.dep;\n'
        f'(\n{clauses}\n);\n'
        'out center tags;'
    )


def categorize(tags: dict) -> str | None:
    """Retrouve la catégorie d'un élément à partir de ses tags OSM."""
    for category, key, regex in POI_FILTERS:
        value = tags.get(key)
        if value and re.match(regex, value):
            return category
    return None


def elements_to_rows(elements: list[dict]) -> list[dict]:
    """Aplatit les éléments Overpass : coordonnées (directes ou centroïde) + tags."""
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        center = el.get("center", {})
        lat = el.get("lat", center.get("lat"))
        lon = el.get("lon", center.get("lon"))
        if lat is None or lon is None:
            continue
        rows.append({
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
            "categorie": categorize(tags),
            "nom": tags.get("name"),
            "latitude": lat,
            "longitude": lon,
            # Bronze : on garde tous les tags bruts pour ne rien perdre
            "tags": json.dumps(tags, ensure_ascii=False),
        })
    return rows


def verifier_reponse(data: dict, dep: str) -> list[dict]:
    """Refuse une réponse Overpass incomplète.

    Quand Overpass dépasse son délai ou manque de mémoire, il répond quand même
    HTTP 200, avec les éléments trouvés jusque-là et un champ `remark`. Sans ce
    contrôle, un jeu de POI tronqué (voire vide) serait enregistré puis publié.
    """
    if not isinstance(data, dict):
        # JSON valide mais pas un objet (null, liste) : ValueError pour que
        # interroger_overpass passe à l'instance suivante.
        raise ValueError(f"Réponse Overpass inattendue pour le {dep} : {type(data).__name__}")
    remarque = data.get("remark")
    if remarque:
        raise ValueError(f"Réponse Overpass incomplète pour le {dep} : {remarque[:200]}")
    elements = data.get("elements") or []
    if not elements:
        raise ValueError(f"Réponse Overpass vide pour le {dep} : aucun point d'intérêt reçu")
    return elements


def interroger_overpass(query: str, dep: str) -> tuple[list[dict], str]:
    """Essaie chaque instance Overpass ; retourne (éléments, URL qui a répondu)."""
    echecs = []
    for url in OVERPASS_MIROIRS:
        try:
            resp = _get_overpass(url, params={"data": query}, timeout=DELAIS_OVERPASS)
            return verifier_reponse(resp.json(), dep), url
        except (requests.RequestException, RetryableHTTPError, ValueError) as exc:
            # ValueError couvre le JSON illisible et les réponses vides ou tronquées
            logger.warning("Overpass %s inutilisable pour le %s (%s)", url, dep, type(exc).__name__)
            echecs.append(f"{url} : {type(exc).__name__}")
    raise OverpassIndisponible(f"Aucune instance Overpass pour le {dep} : " + " ; ".join(echecs))


def ingest(departements: list[str], force: bool = False) -> list[Path]:
    produced: list[Path] = []
    for dep in departements:
        query = build_query(dep)
        source = f"{OVERPASS_URL} FR-{dep}"
        out = BRONZE_DIR / "osm" / f"departement={dep}" / "pois.parquet"
        if already_ingested(out, source=source, force=force, max_age_jours=FRAICHEUR_JOURS):
            produced.append(out)
            continue
        try:
            elements, url = interroger_overpass(query, dep)
        except OverpassIndisponible:
            if not out.exists():
                raise
            # Les points d'intérêt (écoles, gares, commerces) bougent peu d'une
            # semaine à l'autre : mieux vaut un bronze un peu ancien qu'un site figé.
            logger.warning("Overpass indisponible : on garde le bronze OSM existant du %s (%s)", dep, out)
            produced.append(out)
            continue
        df = pd.DataFrame(elements_to_rows(elements))
        atomic_write_parquet(df, out)
        write_manifest(out, source=source, rows=len(df),
                       extra={"departement": dep, "query": query, "instance": url})
        logger.info("OSM %s : %d POI → %s", dep, len(df), out)
        produced.append(out)
    return produced
