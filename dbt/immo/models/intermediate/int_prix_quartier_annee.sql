-- Statistiques de prix par quartier IRIS × type de bien × année
-- (pendant de int_prix_commune_annee à la maille quartier).
-- Les ventes sans quartier (non géolocalisées, géocodage douteux) sont exclues.

select
    code_iris,
    type_bien,
    annee,
    count(*)          as nb_ventes,
    median(prix_m2)   as prix_m2_median,
    avg(latitude)     as latitude,
    avg(longitude)    as longitude
from {{ ref('stg_ventes') }}
where code_iris is not null
group by code_iris, type_bien, annee
