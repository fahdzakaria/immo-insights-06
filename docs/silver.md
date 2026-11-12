# Couche silver — nettoyage & enrichissement

Le silver transforme le bronze brut en tables analysables. **Déterministe et
local** : on recalcule tout à chaque run (pas de re-téléchargement), seul le
cache de géocodage BAN persiste.

```bash
docker compose exec airflow-scheduler bash -c \
  "cd /opt/airflow && python -m pipelines.silver.run_all"
```

```
data/silver/
├── dvf/departement=06/ventes.parquet            # ventes propres
├── ventes_enrichies/departement=06/ventes.parquet  # ⭐ table de faits
├── dpe/departement=06/dpe.parquet
├── osm/departement=06/pois.parquet
├── insee/communes.parquet                        # référentiel socio-éco
├── loyers/communes.parquet                       # loyers par segment
└── geocodage_cache.parquet                       # cache BAN persistant
```

## Règles de nettoyage DVF (dans l'ordre, entonnoir tracé dans le manifeste)

| # | Règle | Justification |
| --- | --- | --- |
| R1 | `nature_mutation` ∈ {Vente, VEFA} | échanges, adjudications, expropriations ≠ prix de marché |
| R2 | `type_local` ∈ {Appartement, Maison} | dépendances et locaux pro hors périmètre |
| R3 | dédoublonnage (mutation, parcelle, type, surface, prix) | DVF répète une ligne par disposition/lot |
| R4 | mutations **mono-logement** uniquement | une mutation à 3 appartements a UNE valeur foncière globale : prix/m² inconstructible |
| R5 | 10 000 € ≤ valeur foncière ≤ 20 M€ | ventes à 1 € symbolique, erreurs de saisie |
| R6 | 8 m² ≤ surface bâtie ≤ 1 000 m² | surfaces nulles ou aberrantes |
| R7 | 500 €/m² ≤ prix/m² ≤ 50 000 €/m² | bornes larges adaptées au marché azuréen |
| R8 | code commune renseigné | indispensable aux jointures |
| R9 | géocodage BAN des ventes sans coordonnées | voir ci-dessous |

Ordre de grandeur (dept 06, 2021-2025) : ~459 k lignes brutes → ~100 k ventes
propres. L'essentiel de l'écart : dépendances (200 k), lignes sans type de
local (78 k), doublons de lots et mutations multi-logements.

## Géocodage BAN (R9)

~1-3 % des ventes DVF n'ont pas de lat/lon. On les résout par lot via
l'endpoint CSV de la BAN (`api-adresse.data.gouv.fr/search/csv/`), score
minimal 0,5, avec un **cache Parquet persistant** : une adresse déjà résolue
n'est plus jamais renvoyée à l'API. La colonne `geocode_source` vaut
`dvf` | `ban` | null (vente conservée même sans géo : elle compte dans les
agrégats communaux, pas dans les analyses de proximité).

## Enrichissements (table `ventes_enrichies`)

1. **Contexte communal** (jointure `code_commune`) : population, évolution
   démographique entre les deux derniers recensements (2017→2023), niveau de vie médian, taux de pauvreté, taux de
   vacance, part de résidences secondaires, emplois salariés (INSEE) + loyer de
   référence €/m² du bon segment — `loyer_m2_ref` = maison ou appartement
   selon le bien (carte des loyers 2025).
2. **Accessibilité** : `nb_education_500m`, `nb_transport_500m`,
   `nb_commerce_500m` — comptage par index spatial cKDTree sur coordonnées
   projetées en mètres (projection équirectangulaire locale, précise à
   l'échelle départementale).
3. **Rapprochement DPE** : DVF ne publie aucun identifiant de logement ; on
   attache donc le DPE **le plus vraisemblable** : même type de bien, à
   < 50 m, surface à ±10 %, **établi avant la vente** (tolérance 30 jours),
   départage par (distance, écart de surface). Méthode probabiliste assumée :
   - `dpe_nb_candidats` et `dpe_ambigu` : en immeuble, plusieurs logements de
     même surface portent des étiquettes différentes ; la vente est alors
     marquée ambiguë et **exclue des analyses par étiquette** ;
   - taux de couverture (48 % sur le 06) et nombre de rapprochements non
     ambigus (23 825) tracés dans le manifeste ; `dpe_distance_m` conservée.

> **Bug corrigé en novembre 2026.** La projection en mètres calculait sa
> latitude de référence séparément pour chaque jeu de points (ventes, DPE,
> POI). Comme x = longitude × R × cos(lat₀), deux références différentes
> décalaient les jeux de 150 à 700 m d'est en ouest : les DPE étaient
> rapprochés du mauvais voisin et les POI comptés autour d'un point décalé.
> La latitude de référence est désormais un paramètre obligatoire, partagé
> par tous les jeux de points (`latitude_reference`), et un test de
> non-régression le vérifie. Effet mesuré : l'écart de prix par étiquette,
> auparavant du bruit (maison F à +19 %), devient cohérent (voir gold).
> Vérifié après correctif : POI recomptés en haversine sur 600 ventes
> (99-100 % identiques), 650 rapprochements DPE sur 650 retrouvés à moins
> de 1 m de la distance enregistrée.

## Nettoyage DPE

Étiquettes A→G valides, type appartement/maison uniquement (les DPE
« immeuble » ne matchent pas une vente individuelle), surface 8-1 000 m²,
dédoublonnage par `numero_dpe` (dernier diagnostic conservé).

## Tests

`tests/test_silver.py` : chaque règle R1→R8 testée individuellement
(paramétrée), dédoublonnage, mutations multi-logements, parsing des décimales
françaises, projection métrique, comptage POI dans le rayon, rapprochement
DPE (cas nominal + cas sans candidat).
