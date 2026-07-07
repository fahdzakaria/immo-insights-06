-- Mart impact DPE : effet de l'étiquette énergétique sur le prix au m².
-- Pour neutraliser l'effet localisation/période, chaque vente est comparée
-- à la médiane de SA commune × type × année ; l'écart médian par étiquette
-- mesure alors la décote/surcote "toutes choses égales par ailleurs".

with reference as (
    select code_commune, type_bien, annee, prix_m2_median
    from {{ ref('int_prix_commune_annee') }}
    where nb_ventes >= 5
),

ventes_dpe as (
    select
        v.code_departement,
        v.type_bien,
        v.etiquette_dpe,
        v.prix_m2,
        v.conso_ep_m2,
        v.prix_m2 / r.prix_m2_median - 1 as ecart_relatif
    from {{ ref('stg_ventes') }} v
    join reference r
      on r.code_commune = v.code_commune
     and r.type_bien   = v.type_bien
     and r.annee       = v.annee
    where v.etiquette_dpe is not null
)

select
    code_departement || '_' || type_bien || '_' || etiquette_dpe as impact_id,
    code_departement,
    type_bien,
    etiquette_dpe,
    count(*)                          as nb_ventes,
    round(median(prix_m2), 0)         as prix_m2_median,
    round(median(ecart_relatif) * 100, 2) as ecart_vs_marche_pct,
    round(median(conso_ep_m2), 0)     as conso_ep_m2_mediane
from ventes_dpe
group by code_departement, type_bien, etiquette_dpe
