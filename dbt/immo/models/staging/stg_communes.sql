-- Référentiel communal : indicateurs INSEE + loyers de référence par segment.
-- Une ligne par commune française (le filtrage par département se fait
-- naturellement à la jointure avec les ventes).

with insee as (
    select * from {{ source('silver', 'insee_communes') }}
),

loyers as (
    select * from {{ source('silver', 'loyers_communes') }}
)

select
    i.code_commune,
    l.nom_commune,
    i.population,
    i.evolution_population_pct,
    i.superficie_km2,
    i.menages,
    i.logements,
    i.taux_logements_vacants,
    i.taux_residences_secondaires,
    i.niveau_vie_median,
    i.taux_pauvrete,
    i.taux_chomage_15_64,
    i.emplois,
    i.etablissements,
    l.loyer_m2_appartement,
    l.loyer_m2_appart_1_2p,
    l.loyer_m2_appart_3p_plus,
    l.loyer_m2_maison,
    l.loyer_m2_appartement_fiabilite,
    l.loyer_m2_maison_fiabilite
from insee i
left join loyers l using (code_commune)
