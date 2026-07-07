# API FastAPI

Swagger interactif : http://localhost:8001/docs

## Endpoints

| Endpoint | Sert | Filtres |
| --- | --- | --- |
| `GET /health` | statut + marts disponibles | — |
| `GET /api/v1/meta` | départements, période couverte | — |
| `GET /api/v1/kpis` | KPIs overview (volumes, prix 12 m, évolutions, rendement) | `departement` |
| `GET /api/v1/communes` | carte + tableau des communes | `departement`, `type_bien`, `prix_m2_min/max`, `population_min`, `recherche`, `tri`, `ordre`, `limit/offset` |
| `GET /api/v1/communes/{code}` | fiche commune (prix, rendement, score) | — |
| `GET /api/v1/tendances` | séries trimestrielles | `departement`, `code_commune`, `type_bien`, `trimestre_min/max` |
| `GET /api/v1/rendement` | rendement locatif par commune | `departement`, `type_bien`, `rendement_min`, `prix_m2_max`, `tri`, pagination |
| `GET /api/v1/dpe/impact` | décote/surcote par étiquette | `departement`, `type_bien` |
| `GET /api/v1/opportunites` | top communes par score | `departement`, `type_bien`, `score_min`, `prix_m2_max`, `limit` |
| `GET /api/v1/estimation` | estimation de prix d'un bien | `code_commune`, `type_bien`, `surface`, `etiquette_dpe` |

## Comment la rapidité est garantie

1. **Marts pré-agrégés** : l'API ne touche jamais les 128 600 ventes — elle
   interroge des marts de quelques centaines de lignes construits par dbt.
2. **Filtrage 100 % en base** : chaque filtre est un `WHERE` paramétré
   DuckDB ; le client ne reçoit jamais plus de 500 lignes (pagination).
3. **Cache TTL 10 min** en mémoire : les marts ne changent qu'une fois par
   jour (DAG à 06:00), les rafales de filtres du front sont absorbées.
4. **DuckDB en mémoire + vues sur Parquet gold** : pas de verrou sur le
   warehouse (le DAG peut écrire pendant que l'API lit), et les vues voient
   automatiquement les fichiers remplacés atomiquement par dbt.

## Sécurité

- Requêtes exclusivement **paramétrées** (placeholders `?`) ;
- tri par **liste blanche** (une colonne inconnue → 422) ;
- validation stricte des entrées (regex codes INSEE, bornes numériques,
  énumérations) via FastAPI/Pydantic ;
- lecture seule : CORS limité à `GET`.

## Estimateur de prix — méthode

Transparente et explicable (pas un modèle boîte noire) :
`prix = surface × prix_m2 médian communal (24 mois) × (1 + écart DPE départemental)`,
fourchette = quartiles p25/p75 locaux, fiabilité = nb de ventes support.
