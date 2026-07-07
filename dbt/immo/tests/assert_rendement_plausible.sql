-- Un rendement locatif brut hors de [0,5 % ; 30 %] signale un problème de
-- données (loyer d'un mauvais segment, prix médian sur trop peu de ventes…).
select *
from {{ ref('mart_rendement_locatif') }}
where rendement_brut_pct is not null
  and (rendement_brut_pct < 0.5 or rendement_brut_pct > 30)
