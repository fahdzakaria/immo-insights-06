-- Mart rendement locatif brut par commune × type de bien :
--   rendement = (loyer €/m² × 12) / prix d'achat €/m².
-- Prix de référence : médiane des ventes des 2 dernières années.
-- Le loyer vient de la carte des loyers 2025 (segment appartement ou maison),
-- avec son indicateur de fiabilité (prédiction à la commune ou à la maille).
-- Le rendement n'est calculé qu'à partir de 5 ventes sur 24 mois : une
-- médiane sur 1-2 ventes produit des rendements absurdes (cas réel : village
-- à une seule vente à 500 €/m² → 45 % de rendement fictif).

with annee_max as (
    select max(annee) as annee_courante from {{ ref('stg_ventes') }}
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
    where annee >= annee_courante - 1
    group by code_commune, type_bien
)

select
    p.code_commune || '_' || p.type_bien as commune_type_id,
    p.code_commune,
    p.nom_commune,
    p.code_departement,
    p.type_bien,
    p.nb_ventes_24m,
    round(p.prix_m2_median, 0) as prix_m2_median,
    case when p.type_bien = 'maison' then c.loyer_m2_maison
         else c.loyer_m2_appartement end as loyer_m2,
    case when p.type_bien = 'maison' then c.loyer_m2_maison_fiabilite
         else c.loyer_m2_appartement_fiabilite end as loyer_fiabilite,
    case when p.nb_ventes_24m >= 5 then
        round(
            (case when p.type_bien = 'maison' then c.loyer_m2_maison
                  else c.loyer_m2_appartement end * 12)
            / nullif(p.prix_m2_median, 0) * 100,
            2
        )
    end as rendement_brut_pct
from prix p
left join {{ ref('stg_communes') }} c using (code_commune)
