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
| `mart_rendement_locatif` | commune × type_bien | rendement brut = loyer×12 / prix m² ; calculé seulement si ≥ 5 ventes/24 mois ; fourchette (intervalle de prédiction du loyer) et drapeau `rendement_fiable` |
| `mart_impact_dpe` | département × type_bien × étiquette | écart de prix **à localisation neutralisée** : chaque vente (DPE non ambigu) comparée à la médiane de sa commune×type×année ; intervalle de confiance à 95 % et drapeau `fiable` |
| `mart_score_investissement` | commune × type_bien (≥ 20 ventes/24 mois) | score 0-100 : 6 composantes en rangs centiles intra-département (prix 20 %, rendement 25 %, dynamique marché 20 %, démo 10 %, services 15 %, tension 10 %) |

## Garde-fous statistiques (leçons des tests)

- **Rendement** : nul si < 5 ventes/24 mois — le test `assert_rendement_plausible`
  a attrapé un village à 1 vente (500 €/m²) donnant 45 % de rendement fictif.
- **Évolutions** : nulles si < 5 ventes de chaque côté de la comparaison.
- **Score** : réservé aux communes à ≥ 20 ventes/24 mois.
- **Rendement fiable** (`rendement_fiable`) : loyer prédit à l'échelle de la
  commune (et non d'une maille plus large, faute d'annonces locales) ET
  ≥ 20 ventes. Dans le 06, 107 communes sur 163 ont un loyer extrapolé pour
  les appartements (144 pour les maisons) : le
  site les écarte par défaut du classement des opportunités (Andon, 11,5 %
  de rendement affiché, repose sur 27 annonces et un loyer de maille).
- **Rendement = majorant** : la carte des loyers donne des loyers d'annonce
  charges comprises. Le mart publie la fourchette issue de l'intervalle de
  prédiction du loyer (Nice : 5,1 %, de 3,9 à 6,8 %). C'est l'intervalle
  d'un loyer individuel prédit, pas l'incertitude sur le loyer moyen de la
  commune, et il n'intègre pas l'incertitude sur le prix médian.
- **Écart DPE fiable** (`fiable`) : ≥ 100 ventes au DPE non ambigu ET écart
  plus grand que son intervalle de confiance. L'estimateur n'applique que
  les écarts fiables.
- **Écart DPE recentré** : les ventes au DPE rapproché sans ambiguïté ne
  sont pas un échantillon neutre (peu de neuf, petits immeubles, ventes plus
  anciennes) ; leur écart médian au marché local vaut +1,3 % pour les
  appartements et −3,5 % pour les maisons (`decalage_echantillon_pct`). Il
  est retranché, sinon une maison C aurait hérité d'une « décote » de 3 %
  qui n'était que le décalage de l'échantillon.
- **Estimateur** : pas d'estimation sous 5 ventes/24 mois ; niveau de
  fiabilité faible (< 20), correcte (< 100), bonne.

## Tests (38, tous verts)

- **Génériques** : `unique`/`not_null` sur toutes les clés, `accepted_values`
  (type_bien, étiquettes A-G, mailles), `relationships` (ventes → communes).
- **Singuliers métier** : rendement ∈ [0,5 ; 30] %, scores ∈ [0 ; 100],
  cohérence p25 ≤ médiane ≤ p75 et bornes de prix silver respectées,
  fourchette de rendement encadrant le rendement central, écart DPE
  « fiable » reposant bien sur ≥ 100 ventes et distinct de zéro.

## Résultats notables (dept 06)

- Écart de prix par étiquette DPE, par rapport à un logement comparable du
  même marché local au DPE connu. Appartements, monotone : A +20,8 % (±5,8),
  B +9,3 %, C +4,5 %, D −5,2 %, E −5,2 %, F −6,4 %, G −9,4 % (±4,0).
  Maisons : A +12,6 %, B +5,7 %, D −2,6 %, E −3,6 %, F −7,9 % ; C (+0,4 %
  ± 1,9) et G (+2,4 % ± 8,4, 125 ventes) ne sont pas distincts de zéro.
- Rendements bruts les plus élevés parmi les loyers mesurés localement :
  Puget-Théniers 10,3 %, Lucéram 8,8 %, Drap 7,3 %. Les rendements à deux
  chiffres de l'arrière-pays (Andon 11,5 %, Tende 10,6 %) reposent sur des
  loyers extrapolés : marqués non fiables.

## Année de référence

Les fenêtres « 24 mois » et les évolutions 1 an / 3 ans s'appuient sur
`int_annee_reference` : la **dernière année complète** (qui contient des
ventes en décembre). DVF étant publié par semestre, l'arrivée du 1er semestre
de l'année en cours ne décale donc pas ces calculs ; ses trimestres
apparaissent seulement dans `mart_evolution_trimestrielle`.

## Limites connues de l'écart DPE

- **Rapprochement probabiliste** : la distance médiane vente↔DPE est de 21 m
  (parcelle DVF contre adresse BAN) ; un rapprochement « non ambigu » peut
  encore désigner un logement voisin. 22 à 27 % des DPE retenus ont plus
  d'un an à la date de vente.
- **Échantillon** : 65 % des appartements rapprochés sont ambigus (79 % en
  2025, car le stock de DPE grossit) et exclus. L'échantillon gardé
  sur-représente les petits immeubles et les ventes anciennes ; il rétrécira
  avec le temps.
- **Intervalle de confiance** : formule normale sur la médiane, ventes
  supposées indépendantes. Un bootstrap par parcelle élargit l'intervalle
  d'environ 50 % pour les appartements C et D. 14 étiquettes testées sans
  correction de multiplicité.
- **Pas causal** : l'écart mélange énergie, âge du bâtiment et état général.
