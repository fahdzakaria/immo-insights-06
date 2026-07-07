"""CLI silver — enchaîne nettoyages puis enrichissement, dans le bon ordre.

    python -m pipelines.silver.run_all [--departements 06,83]

Contrairement au bronze (téléchargements coûteux, idempotence par manifeste),
le silver est DÉTERMINISTE et local : on recalcule tout à chaque run, seul le
cache de géocodage BAN persiste (pour ne jamais re-payer l'API).
"""

import argparse
import logging
import sys

from pipelines import config
from pipelines.silver import dpe_clean, dvf_clean, enrichissement, osm_clean, referentiels

ETAPES = [
    ("referentiels", referentiels.build),
    ("dpe", dpe_clean.build),
    ("osm", osm_clean.build),
    ("dvf", dvf_clean.build),
    ("enrichissement", enrichissement.build),  # dépend de toutes les étapes précédentes
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construction de la couche silver")
    parser.add_argument("--departements", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    deps = [d.strip() for d in args.departements.split(",")] if args.departements else config.departements()

    for nom, build in ETAPES:
        logging.info("=== Étape silver : %s ===", nom)
        build(deps)
    logging.info("Couche silver construite (départements %s)", deps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
