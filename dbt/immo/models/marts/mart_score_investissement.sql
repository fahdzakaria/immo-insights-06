-- Mart score d'investissement (0-100) par commune × type de bien.
-- Croise 6 composantes, chacune en rang centile PARMI LES COMMUNES DU MÊME
-- DÉPARTEMENT (comparer Nice à un village de montagne n'aurait pas de sens
-- hors de ce cadre relatif) :
--   prix_accessible  (20%) : prix au m² bas
--   rendement        (25%) : rendement locatif brut élevé
--   dynamique_marche (20%) : prix en hausse sur 3 ans
--   dynamique_demo   (10%) : population en croissance
--   services         (15%) : écoles/transports/commerces proches des biens vendus
--   tension          (10%) : peu de logements vacants
-- Seules les communes avec ≥ 20 ventes sur 24 mois sont scorées.

with services as (
    select
        code_commune,
        type_bien,
        avg(nb_education_500m + nb_transport_500m + nb_commerce_500m) as pois_moyens
    from {{ ref('stg_ventes') }}
    group by code_commune, type_bien
),

base as (
    select
        p.code_commune,
        p.nom_commune,
        p.code_departement,
        p.type_bien,
        p.nb_ventes_24m,
        p.prix_m2_median,
        r.rendement_brut_pct,
        p.evolution_3ans_pct,
        c.evolution_population_pct,
        c.taux_logements_vacants,
        s.pois_moyens
    from {{ ref('mart_prix_m2_par_commune') }} p
    join {{ ref('mart_rendement_locatif') }} r using (commune_type_id)
    left join {{ ref('stg_communes') }} c on c.code_commune = p.code_commune
    left join services s
        on s.code_commune = p.code_commune and s.type_bien = p.type_bien
    where p.nb_ventes_24m >= 20
),

rangs as (
    select
        *,
        1 - percent_rank() over (partition by code_departement, type_bien order by prix_m2_median)          as sc_prix,
        percent_rank() over (partition by code_departement, type_bien order by rendement_brut_pct nulls first) as sc_rendement,
        percent_rank() over (partition by code_departement, type_bien order by evolution_3ans_pct nulls first) as sc_marche,
        percent_rank() over (partition by code_departement, type_bien order by evolution_population_pct nulls first) as sc_demo,
        percent_rank() over (partition by code_departement, type_bien order by pois_moyens nulls first)     as sc_services,
        1 - percent_rank() over (partition by code_departement, type_bien order by taux_logements_vacants nulls last) as sc_tension
    from base
)

select
    code_commune || '_' || type_bien as commune_type_id,
    code_commune,
    nom_commune,
    code_departement,
    type_bien,
    nb_ventes_24m,
    prix_m2_median,
    rendement_brut_pct,
    evolution_3ans_pct,
    evolution_population_pct,
    taux_logements_vacants,
    round(pois_moyens, 1) as pois_moyens_500m,
    round(sc_prix * 100)      as score_prix,
    round(sc_rendement * 100) as score_rendement,
    round(sc_marche * 100)    as score_dynamique_marche,
    round(sc_demo * 100)      as score_dynamique_demo,
    round(sc_services * 100)  as score_services,
    round(sc_tension * 100)   as score_tension,
    round((
        0.20 * sc_prix +
        0.25 * sc_rendement +
        0.20 * sc_marche +
        0.10 * sc_demo +
        0.15 * sc_services +
        0.10 * sc_tension
    ) * 100) as score_investissement
from rangs
