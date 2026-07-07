-- Tous les scores (global et composantes) doivent rester dans [0 ; 100].
select *
from {{ ref('mart_score_investissement') }}
where score_investissement not between 0 and 100
   or score_prix not between 0 and 100
   or score_rendement not between 0 and 100
   or score_dynamique_marche not between 0 and 100
   or score_dynamique_demo not between 0 and 100
   or score_services not between 0 and 100
   or score_tension not between 0 and 100
