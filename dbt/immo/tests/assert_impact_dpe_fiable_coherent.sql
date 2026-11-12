-- Un écart DPE marqué « fiable » doit reposer sur assez de ventes et être
-- distinct de zéro (plus grand que son intervalle de confiance).
select *
from {{ ref('mart_impact_dpe') }}
where fiable
  and (nb_ventes < {{ var('seuil_ventes_dpe') }} or abs(ecart_vs_marche_pct) <= ecart_ic95_pct)
