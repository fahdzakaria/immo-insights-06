"""CLI d'ingestion bronze — point d'entrée unique, rejouable sans doublon.

Exemples :
    python -m pipelines.ingestion.run_all                      # tout, départements de la config
    python -m pipelines.ingestion.run_all --sources dvf,dpe    # sources choisies
    python -m pipelines.ingestion.run_all --departements 06,83 --force
"""

import argparse
import logging
import sys

from pipelines import config
from pipelines.ingestion import dpe, dvf, insee, loyers, osm

SOURCES = {
    "dvf": dvf.ingest,
    "insee": insee.ingest,
    "loyers": loyers.ingest,
    "dpe": dpe.ingest,
    "osm": osm.ingest,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestion bronze (Parquet)")
    parser.add_argument("--sources", default=",".join(SOURCES),
                        help=f"Sources à ingérer parmi : {', '.join(SOURCES)}")
    parser.add_argument("--departements", default=None,
                        help="Codes départements (défaut : variable DEPARTEMENTS)")
    parser.add_argument("--force", action="store_true",
                        help="Re-télécharge même si déjà ingéré")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    deps = [d.strip() for d in args.departements.split(",")] if args.departements else config.departements()
    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = set(wanted) - set(SOURCES)
    if unknown:
        parser.error(f"Sources inconnues : {unknown}")

    failures = []
    for name in wanted:
        try:
            paths = SOURCES[name](deps, force=args.force)
            logging.info("✔ %s : %d fichier(s) bronze", name, len(paths))
        except Exception:
            logging.exception("✘ %s : échec", name)
            failures.append(name)

    if failures:
        logging.error("Sources en échec : %s", failures)
        return 1
    logging.info("Ingestion bronze terminée sans erreur (départements %s)", deps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
