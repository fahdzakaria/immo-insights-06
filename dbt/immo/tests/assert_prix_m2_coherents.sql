-- Cohérence des marts de prix : la médiane doit rester dans les bornes du
-- nettoyage silver (500-50 000 €/m²) et p25 ≤ médiane ≤ p75.
select *
from {{ ref('mart_prix_m2_par_commune') }}
where prix_m2_median is not null
  and (
    prix_m2_median < 500 or prix_m2_median > 50000
    or prix_m2_p25 > prix_m2_median
    or prix_m2_p75 < prix_m2_median
  )
