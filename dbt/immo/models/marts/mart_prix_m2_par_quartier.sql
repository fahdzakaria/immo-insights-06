-- Mart « maille quartier » : une ligne par quartier IRIS × type de bien, pour
-- les communes que l'INSEE découpe en quartiers (Nice, Cannes, Antibes…).
-- Même logique que mart_prix_m2_par_commune (médiane et quartiles sur les
-- 2 dernières années complètes, évolutions 1 an / 3 ans), avec deux
-- différences assumées :
--   * tous les quartiers sont présents, même sans vente : la carte doit
--     pouvoir les dessiner « éteints » ;
--   * les prix sont NULS sous le seuil d'affichage (5 ventes / 24 mois).
--     À cette maille les petits effectifs sont la règle (maisons en ville) :
--     le garde-fou est dans la donnée, pas seulement dans l'interface.

{% set seuil_affichage = var('seuil_ventes_affichage') %}
{% set seuil_fiable = var('seuil_ventes_fiable') %}

with annee_max as (
    select annee_courante from {{ ref('int_annee_reference') }}
),

quartiers as (
    select q.code_iris, q.nom_iris, q.type_iris, q.code_commune, q.nom_commune, t.type_bien
    from {{ ref('stg_iris') }} q
    cross join (select unnest(['appartement', 'maison']) as type_bien) t
    where q.nb_iris_commune > 1
),

-- Département déduit du code commune (2 premiers caractères, 2A/2B compris) :
-- une commune découpée sans aucune vente garde ainsi son département
departements as (
    select distinct code_commune, left(code_commune, 2) as code_departement
    from {{ ref('stg_iris') }}
),

par_annee as (
    select * from {{ ref('int_prix_quartier_annee') }}
),

totaux as (
    select
        code_iris,
        type_bien,
        sum(nb_ventes)::bigint                        as nb_ventes_total,
        sum(latitude * nb_ventes) / sum(nb_ventes)    as latitude,
        sum(longitude * nb_ventes) / sum(nb_ventes)   as longitude
    from par_annee
    group by code_iris, type_bien
),

-- Prix de référence : 2 dernières années COMPLÈTES
recent as (
    select
        v.code_iris,
        v.type_bien,
        count(*)            as nb_ventes_24m,
        median(v.prix_m2)   as prix_m2_median,
        percentile_cont(0.25) within group (order by v.prix_m2) as prix_m2_p25,
        percentile_cont(0.75) within group (order by v.prix_m2) as prix_m2_p75,
        median(v.surface_bati)    as surface_mediane,
        median(v.valeur_fonciere) as prix_median
    from {{ ref('stg_ventes') }} v
    cross join annee_max
    where v.code_iris is not null
      and v.annee between annee_max.annee_courante - 1 and annee_max.annee_courante
    group by v.code_iris, v.type_bien
),

-- Évolutions : médiane année courante vs N-1 et vs N-3 (min. 5 ventes de chaque côté)
evolutions as (
    select
        a0.code_iris,
        a0.type_bien,
        case when a0.nb_ventes >= {{ seuil_affichage }} and a1.nb_ventes >= {{ seuil_affichage }}
             then round((a0.prix_m2_median / a1.prix_m2_median - 1) * 100, 2) end as evolution_1an_pct,
        case when a0.nb_ventes >= {{ seuil_affichage }} and a3.nb_ventes >= {{ seuil_affichage }}
             then round((a0.prix_m2_median / a3.prix_m2_median - 1) * 100, 2) end as evolution_3ans_pct
    from par_annee a0
    cross join annee_max
    left join par_annee a1
        on a1.code_iris = a0.code_iris and a1.type_bien = a0.type_bien
       and a1.annee = a0.annee - 1
    left join par_annee a3
        on a3.code_iris = a0.code_iris and a3.type_bien = a0.type_bien
       and a3.annee = a0.annee - 3
    where a0.annee = annee_max.annee_courante
),

assemble as (
    select
        q.*,
        d.code_departement,
        coalesce(t.nb_ventes_total, 0) as nb_ventes_total,
        coalesce(r.nb_ventes_24m, 0)   as nb_ventes_24m,
        coalesce(r.nb_ventes_24m, 0) >= {{ seuil_affichage }} as affichable,
        r.prix_m2_median, r.prix_m2_p25, r.prix_m2_p75, r.prix_median, r.surface_mediane,
        e.evolution_1an_pct, e.evolution_3ans_pct,
        t.latitude, t.longitude,
        -- Repère communal soumis au même seuil que la commune elle-même
        case when c.nb_ventes_24m >= {{ seuil_affichage }} then c.prix_m2_median end as prix_m2_median_commune
    from quartiers q
    left join departements d using (code_commune)
    left join totaux t using (code_iris, type_bien)
    left join recent r using (code_iris, type_bien)
    left join evolutions e using (code_iris, type_bien)
    left join {{ ref('mart_prix_m2_par_commune') }} c using (code_commune, type_bien)
)

select
    code_iris || '_' || type_bien as quartier_type_id,
    code_iris,
    nom_iris,
    type_iris,
    code_commune,
    nom_commune,
    code_departement,
    type_bien,
    nb_ventes_total,
    nb_ventes_24m,
    -- Fiabilité : au moins {{ seuil_fiable }} ventes sur 24 mois (même seuil que le rendement)
    nb_ventes_24m >= {{ seuil_fiable }} as fiable,
    case when affichable then round(prix_m2_median, 0) end  as prix_m2_median,
    case when affichable then round(prix_m2_p25, 0) end     as prix_m2_p25,
    case when affichable then round(prix_m2_p75, 0) end     as prix_m2_p75,
    case when affichable then round(prix_median, 0) end     as prix_median,
    case when affichable then round(surface_mediane, 0) end as surface_mediane,
    case when affichable then evolution_1an_pct end         as evolution_1an_pct,
    case when affichable then evolution_3ans_pct end        as evolution_3ans_pct,
    -- Repère : la médiane de la commune, et l'écart du quartier à celle-ci
    prix_m2_median_commune,
    case when affichable and prix_m2_median_commune > 0
         then round((prix_m2_median / prix_m2_median_commune - 1) * 100, 1) end as ecart_commune_pct,
    latitude,
    longitude
from assemble
