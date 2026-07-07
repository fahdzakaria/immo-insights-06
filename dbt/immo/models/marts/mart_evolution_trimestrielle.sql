-- Mart tendances : volumes et prix médians par trimestre, à deux mailles
-- (commune et département) via GROUPING SETS — le front choisit sa maille
-- sans agréger côté client.

select
    coalesce(code_commune, code_departement) || '_' || trimestre || '_' || type_bien as evolution_id,
    case when code_commune is null then 'departement' else 'commune' end as maille,
    code_departement,
    code_commune,
    any_value(nom_commune)  as nom_commune,
    type_bien,
    trimestre,
    min(annee)              as annee,
    count(*)                as nb_ventes,
    round(median(prix_m2), 0)          as prix_m2_median,
    round(median(valeur_fonciere), 0)  as prix_median,
    round(median(surface_bati), 0)     as surface_mediane
from {{ ref('stg_ventes') }}
group by grouping sets (
    (code_departement, trimestre, type_bien),
    (code_departement, code_commune, trimestre, type_bien)
)
