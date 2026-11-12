-- La fourchette de rendement (issue de l'intervalle de prédiction du loyer)
-- doit encadrer le rendement central : bas ≤ central ≤ haut.
select *
from {{ ref('mart_rendement_locatif') }}
where rendement_brut_pct is not null
  and (
    rendement_bas_pct is null or rendement_haut_pct is null
    or rendement_bas_pct > rendement_brut_pct
    or rendement_haut_pct < rendement_brut_pct
  )
