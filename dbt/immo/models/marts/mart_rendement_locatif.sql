-- Mart rendement locatif brut par commune × type de bien :
--   rendement = (loyer €/m² × 12) / prix d'achat €/m².
-- Prix de référence : médiane des ventes des 2 dernières années complètes.
-- Le loyer vient de la carte des loyers 2025 (segment appartement ou maison).
--
-- LIMITES ASSUMÉES — la carte des loyers donne des loyers D'ANNONCE, CHARGES
-- COMPRISES : le rendement affiché est donc un majorant du rendement réel
-- hors charges. Deux garde-fous pour ne pas sur-vendre le chiffre :
--  1. fourchette : la carte publie un intervalle de prédiction du loyer
--     (loyer_m2_bas / loyer_m2_haut) → rendement_bas_pct / rendement_haut_pct ;
--  2. rendement_fiable : vrai seulement si le loyer est prédit à l'échelle de
--     la COMMUNE (et non d'une maille plus large, faute d'annonces locales)
--     ET si le prix repose sur au moins {{ var('seuil_ventes_fiable') }} ventes.
-- Le rendement n'est calculé qu'à partir de 5 ventes sur 24 mois : une
-- médiane sur 1-2 ventes produit des rendements absurdes (cas réel : village
-- à une seule vente à 500 €/m² → 45 % de rendement fictif).

with annee_max as (
    select annee_courante from {{ ref('int_annee_reference') }}
),

prix as (
    select
        code_commune,
        any_value(nom_commune)      as nom_commune,
        any_value(code_departement) as code_departement,
        type_bien,
        count(*)                    as nb_ventes_24m,
        median(prix_m2)             as prix_m2_median
    from {{ ref('stg_ventes') }}
    cross join annee_max
    where annee between annee_courante - 1 and annee_courante
    group by code_commune, type_bien
),

loyers as (
    select
        p.*,
        case when p.type_bien = 'maison' then c.loyer_m2_maison            else c.loyer_m2_appartement            end as loyer_m2,
        case when p.type_bien = 'maison' then c.loyer_m2_maison_bas        else c.loyer_m2_appartement_bas        end as loyer_m2_bas,
        case when p.type_bien = 'maison' then c.loyer_m2_maison_haut       else c.loyer_m2_appartement_haut       end as loyer_m2_haut,
        case when p.type_bien = 'maison' then c.loyer_m2_maison_fiabilite  else c.loyer_m2_appartement_fiabilite  end as loyer_fiabilite,
        case when p.type_bien = 'maison' then c.loyer_m2_maison_nb_annonces else c.loyer_m2_appartement_nb_annonces end as loyer_nb_annonces
    from prix p
    left join {{ ref('stg_communes') }} c using (code_commune)
)

select
    code_commune || '_' || type_bien as commune_type_id,
    code_commune,
    nom_commune,
    code_departement,
    type_bien,
    nb_ventes_24m,
    round(prix_m2_median, 0) as prix_m2_median,
    loyer_m2,
    loyer_m2_bas,
    loyer_m2_haut,
    loyer_fiabilite,
    cast(loyer_nb_annonces as integer) as loyer_nb_annonces,
    case when nb_ventes_24m >= 5 then round(loyer_m2      * 12 / nullif(prix_m2_median, 0) * 100, 2) end as rendement_brut_pct,
    case when nb_ventes_24m >= 5 then round(loyer_m2_bas  * 12 / nullif(prix_m2_median, 0) * 100, 2) end as rendement_bas_pct,
    case when nb_ventes_24m >= 5 then round(loyer_m2_haut * 12 / nullif(prix_m2_median, 0) * 100, 2) end as rendement_haut_pct,
    coalesce(loyer_fiabilite = 'commune' and nb_ventes_24m >= {{ var('seuil_ventes_fiable') }}, false) as rendement_fiable
from loyers
