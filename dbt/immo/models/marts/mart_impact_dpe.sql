-- Mart impact DPE : écart de prix au m² observé selon l'étiquette énergétique.
-- Pour neutraliser l'effet localisation/période, chaque vente est comparée
-- à la médiane de SA commune × type × année, puis l'écart est recentré sur
-- l'échantillon (voir CTE `centre`) : ecart_vs_marche_pct mesure la
-- décote/surcote d'une étiquette par rapport à un logement comparable du même
-- marché local dont le DPE est connu.
--
-- Fiabilité :
--  - seules les ventes au DPE rapproché SANS AMBIGUÏTÉ comptent (dpe_ambigu =
--    false) : en immeuble, plusieurs logements de même surface portent des
--    étiquettes différentes et le rapprochement géographique ne peut pas
--    trancher — les garder noierait l'effet dans le bruit ;
--  - ecart_ic95_pct : demi-largeur de l'intervalle de confiance à 95 % de
--    l'écart médian (erreur-type d'une médiane ≈ 1,2533 × σ / √n, avec σ
--    estimé de façon robuste par 1,4826 × MAD) ;
--  - fiable : au moins {{ var('seuil_ventes_dpe') }} ventes ET un écart plus grand que son
--    intervalle de confiance (distinct de zéro). Sinon l'écart est publié à
--    titre indicatif mais l'estimateur ne l'applique pas.
-- Limites : c'est un écart OBSERVÉ, pas un effet causal de l'énergie seule —
-- les étiquettes A/B sont surtout des logements récents. L'intervalle de
-- confiance suppose des ventes indépendantes ; elles sont groupées par
-- immeuble, l'incertitude réelle est donc un peu plus large (≈ ×1,5 pour les
-- appartements C et D d'après un bootstrap par parcelle).

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
        v.prix_m2 / r.prix_m2_median - 1 as ecart_brut
    from {{ ref('stg_ventes') }} v
    join reference r
      on r.code_commune = v.code_commune
     and r.type_bien   = v.type_bien
     and r.annee       = v.annee
    where v.etiquette_dpe is not null
      and v.dpe_ambigu = false
),

-- Recentrage : les ventes au DPE rapproché sans ambiguïté ne sont pas un
-- échantillon neutre du marché (peu de neuf, petits immeubles…) : leur écart
-- médian au marché local n'est pas nul (maisons : environ −3 %). On le
-- retranche pour que l'écart mesure l'effet de l'ÉTIQUETTE, par rapport à un
-- logement comparable au DPE connu, et non le décalage de l'échantillon.
centre as (
    select
        *,
        median(ecart_brut) over (partition by code_departement, type_bien) as decalage_echantillon,
        ecart_brut - median(ecart_brut) over (partition by code_departement, type_bien) as ecart_relatif
    from ventes_dpe
)

select
    code_departement || '_' || type_bien || '_' || etiquette_dpe as impact_id,
    code_departement,
    type_bien,
    etiquette_dpe,
    count(*)                          as nb_ventes,
    round(median(prix_m2), 0)         as prix_m2_median,
    round(median(ecart_relatif) * 100, 2) as ecart_vs_marche_pct,
    round(1.96 * 1.2533 * 1.4826 * mad(ecart_relatif) / sqrt(count(*)) * 100, 2) as ecart_ic95_pct,
    count(*) >= {{ var('seuil_ventes_dpe') }}
        and abs(median(ecart_relatif)) > 1.96 * 1.2533 * 1.4826 * mad(ecart_relatif) / sqrt(count(*)) as fiable,
    round(any_value(decalage_echantillon) * 100, 2) as decalage_echantillon_pct,
    round(median(conso_ep_m2), 0)     as conso_ep_m2_mediane
from centre
group by code_departement, type_bien, etiquette_dpe
