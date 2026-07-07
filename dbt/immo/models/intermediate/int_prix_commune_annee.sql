-- Brique réutilisée par plusieurs marts : statistiques de prix
-- par commune × type de bien × année.

select
    code_commune,
    any_value(nom_commune)        as nom_commune,
    any_value(code_departement)   as code_departement,
    type_bien,
    annee,
    count(*)                      as nb_ventes,
    median(prix_m2)               as prix_m2_median,
    percentile_cont(0.25) within group (order by prix_m2) as prix_m2_p25,
    percentile_cont(0.75) within group (order by prix_m2) as prix_m2_p75,
    median(valeur_fonciere)       as prix_median,
    median(surface_bati)          as surface_mediane,
    avg(latitude)                 as latitude,
    avg(longitude)                as longitude
from {{ ref('stg_ventes') }}
group by code_commune, type_bien, annee
