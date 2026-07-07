# Couche gold — data marts dbt

## Architecture

Le projet dbt (`dbt/immo`) lit les Parquet **silver** comme sources externes
DuckDB (aucune copie), et matérialise les marts en `external` : chaque mart
est écrit en **Parquet dans `data/gold/`** et exposé comme **vue dans le
warehouse `data/warehouse/immo.duckdb`** — le lac et le warehouse restent
synchrones par construction.

```
sources (silver/*.parquet)
  → staging   : stg_ventes, stg_communes            (vues, typage/renommage)
  → intermediate : int_prix_commune_annee           (vue, stats réutilisées)
  → marts     : 5 tables gold                       (parquet + vue)
```

```bash
docker compose exec airflow-scheduler bash -c \
  "cd /opt/airflow/dbt/immo && dbt build --profiles-dir ."   # run + tests
docker compose exec airflow-scheduler bash -c \
  "cd /opt/airflow/dbt/immo && dbt docs generate --profiles-dir ."
```

## Les 5 marts

| Mart | Grain | Sert |
| --- | --- | --- |
| `mart_prix_m2_par_commune` | commune × type_bien | carte choroplèthe, comparateur — médiane/quartiles 24 mois, évolutions 1 an & 3 ans, centroïde |
| `mart_evolution_trimestrielle` | (commune \| département) × trimestre × type_bien | tendances — GROUPING SETS : deux mailles pré-agrégées, le front ne ré-agrège jamais |
| `mart_rendement_locatif` | commune × type_bien | rendement brut = loyer×12 / prix m² ; calculé seulement si ≥ 5 ventes/24 mois |
| `mart_impact_dpe` | département × type_bien × étiquette | décote énergétique **à localisation neutralisée** : chaque vente comparée à la médiane de sa commune×type×année |
| `mart_score_investissement` | commune × type_bien (≥ 20 ventes/24 mois) | score 0-100 : 6 composantes en rangs centiles intra-département (prix 20 %, rendement 25 %, dynamique marché 20 %, démo 10 %, services 15 %, tension 10 %) |

## Garde-fous statistiques (leçons des tests)

- **Rendement** : nul si < 5 ventes/24 mois — le test `assert_rendement_plausible`
  a attrapé un village à 1 vente (500 €/m²) donnant 45 % de rendement fictif.
- **Évolutions** : nulles si < 5 ventes de chaque côté de la comparaison.
- **Score** : réservé aux communes à ≥ 20 ventes/24 mois.

## Tests (32, tous verts)

- **Génériques** : `unique`/`not_null` sur toutes les clés, `accepted_values`
  (type_bien, étiquettes A-G, mailles), `relationships` (ventes → communes).
- **Singuliers métier** : rendement ∈ [0,5 ; 30] %, scores ∈ [0 ; 100],
  cohérence p25 ≤ médiane ≤ p75 et bornes de prix silver respectées.

## Résultats notables (dept 06)

- Décote DPE à localisation neutralisée, quasi monotone : B +0,2 % → G −1,8 %
  vs marché local (la décote azuréenne est plus faible que la moyenne
  nationale : le foncier domine la valeur).
- Meilleurs rendements bruts : arrière-pays (Andon 11,5 %, Tende 10,6 %) —
  prix bas, loyers soutenus.
