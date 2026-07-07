-- Mart carte + comparateur : une ligne par commune × type de bien,
-- avec prix médians, dispersion, évolutions 1 an / 3 ans et centroïde
-- pour la carte choroplèthe.

with par_annee as (
    select * from {{ ref('int_prix_commune_annee') }}
),

annee_max as (
    select max(annee) as annee_courante from par_annee
),

totaux as (
    select
        code_commune,
        any_value(nom_commune)      as nom_commune,
        any_value(code_departement) as code_departement,
        type_bien,
        sum(nb_ventes)              as nb_ventes_total,
        avg(latitude)               as latitude,
        avg(longitude)              as longitude
    from par_annee
    group by code_commune, type_bien
),

-- Prix de référence : médiane sur les 2 dernières années (volume + fraîcheur)
recent as (
    select
        v.code_commune,
        v.type_bien,
        count(*)            as nb_ventes_24m,
        median(v.prix_m2)   as prix_m2_median,
        percentile_cont(0.25) within group (order by v.prix_m2) as prix_m2_p25,
        percentile_cont(0.75) within group (order by v.prix_m2) as prix_m2_p75,
        median(v.surface_bati) as surface_mediane,
        median(v.valeur_fonciere) as prix_median
    from {{ ref('stg_ventes') }} v
    cross join annee_max
    where v.annee >= annee_max.annee_courante - 1
    group by v.code_commune, v.type_bien
),

-- Évolutions : médiane année courante vs N-1 et vs N-3 (min. 5 ventes de chaque côté)
evolutions as (
    select
        a0.code_commune,
        a0.type_bien,
        case when a0.nb_ventes >= 5 and a1.nb_ventes >= 5
             then round((a0.prix_m2_median / a1.prix_m2_median - 1) * 100, 2) end as evolution_1an_pct,
        case when a0.nb_ventes >= 5 and a3.nb_ventes >= 5
             then round((a0.prix_m2_median / a3.prix_m2_median - 1) * 100, 2) end as evolution_3ans_pct
    from par_annee a0
    cross join annee_max
    left join par_annee a1
        on a1.code_commune = a0.code_commune and a1.type_bien = a0.type_bien
       and a1.annee = a0.annee - 1
    left join par_annee a3
        on a3.code_commune = a0.code_commune and a3.type_bien = a0.type_bien
       and a3.annee = a0.annee - 3
    where a0.annee = annee_max.annee_courante
)

select
    t.code_commune || '_' || t.type_bien as commune_type_id,
    t.code_commune,
    t.nom_commune,
    t.code_departement,
    t.type_bien,
    t.nb_ventes_total,
    r.nb_ventes_24m,
    round(r.prix_m2_median, 0)  as prix_m2_median,
    round(r.prix_m2_p25, 0)     as prix_m2_p25,
    round(r.prix_m2_p75, 0)     as prix_m2_p75,
    round(r.prix_median, 0)     as prix_median,
    round(r.surface_mediane, 0) as surface_mediane,
    e.evolution_1an_pct,
    e.evolution_3ans_pct,
    t.latitude,
    t.longitude,
    c.population,
    c.niveau_vie_median,
    c.taux_pauvrete
from totaux t
left join recent r using (code_commune, type_bien)
left join evolutions e using (code_commune, type_bien)
left join {{ ref('stg_communes') }} c using (code_commune)
