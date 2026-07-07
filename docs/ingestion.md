# Couche bronze — ingestion des sources

## Principe

La couche bronze stocke les données **telles que téléchargées** (aucun
nettoyage, aucun filtrage métier), en Parquet, partitionnées par département
quand la source le permet. Toute règle de transformation vit en silver — si
une règle de nettoyage change, on rejoue silver sans re-télécharger.

```
data/bronze/
├── dvf/departement=06/annee=2024/dvf.parquet        # 1 fichier / dept / an
├── dpe/departement=06/dpe.parquet                    # 1 fichier / dept
├── osm/departement=06/pois.parquet                   # 1 fichier / dept
├── insee/base_comparateur.parquet (+ _meta)          # national
└── loyers/{appartement,appartement_1_2p,appartement_3p_plus,maison}.parquet  # national
```

## Idempotence & fraîcheur

Chaque Parquet est accompagné d'un manifeste JSON (`*.manifest.json`) qui
trace l'URL source, la date d'ingestion et la volumétrie. Rejouer l'ingestion
**ne re-télécharge pas** une source dont le manifeste correspond déjà —
`--force` outrepasse. Les écritures sont atomiques (tmp + rename) : un job
interrompu ne laisse jamais de Parquet corrompu.

**Politique de fraîcheur** : les sources publiques sont republiées sous des
URLs *stables* (DVF « latest », API ADEME…) — sans garde-fou, le bronze
resterait figé au premier téléchargement. Chaque module définit donc un
`FRAICHEUR_JOURS` au-delà duquel le run quotidien re-télécharge :

| Source | TTL | Rythme réel de la source |
| --- | --- | --- |
| DPE, OSM | 7 j | mises à jour continues |
| DVF | 15 j | republication ~2×/an (avril, octobre) |
| INSEE, loyers | 30 j | millésimes annuels |

## Lancer

```bash
docker compose exec airflow-scheduler bash -c \
  "cd /opt/airflow && python -m pipelines.ingestion.run_all"

# Options
python -m pipelines.ingestion.run_all --sources dvf,dpe --departements 06,83 --force
```

## Sources

| Source | Mode d'accès | Particularités |
| --- | --- | --- |
| **DVF géolocalisé** | CSV.gz statique par année/département (`files.data.gouv.fr/geo-dvf`) | Fenêtre glissante ~5 ans : un 404 sur une année est ignoré (warning). Années paramétrables via `DVF_ANNEES`. |
| **DPE** (ADEME) | API data-fair, dataset `dpe03existant` (~15 M lignes) | Filtré côté API par `code_departement_ban`, sélection de 18 colonnes sur 200+, pagination par curseur `after` (10 000 lignes/page). |
| **INSEE** comparateur | Zip national (`base_cc_comparateur_csv.zip`) | Population, médiane du niveau de vie, pauvreté… par commune. Le dictionnaire de variables du zip est aussi conservé. |
| **Carte des loyers** | 4 CSV nationaux via liens permanents data.gouv (`/datasets/r/{id}`) | Millésime 2025. Tout est lu en texte (décimales à virgule) : parsing en silver. |
| **OSM** (Overpass) | Requête QL sur la zone ISO3166-2 du département | 3 catégories : education, transport, commerce. `nwr … out center` pour avoir un centroïde même sur les bâtiments-polygones. Tags bruts conservés en JSON. |

## Choix techniques

- **Codes INSEE/postaux toujours en texte** : `06004` ne doit jamais devenir
  `6004`. Testé unitairement.
- **Téléchargements en mémoire** : la plus grosse source par département fait
  < 200 Mo, inutile de gérer des fichiers temporaires.
- **Retry exponentiel** (5 tentatives, 2 s → 60 s) sur erreurs réseau, 5xx et
  429 : les APIs publiques (Overpass notamment) limitent le débit.
- **User-Agent identifiable** sur toutes les requêtes, conformément aux
  chartes d'usage BAN/Overpass.

## Tests

```bash
docker compose exec airflow-scheduler bash -c "cd /opt/airflow && python -m pytest tests/ -v"
```

Les tests sont 100 % hors-ligne (aucun appel réseau) : construction d'URLs,
parsing des réponses API sur fixtures, catégorisation OSM, idempotence et
atomicité des écritures, préservation des zéros de tête.
