-- Garde-fous de la maille quartier : aucun chiffre sous 5 ventes / 24 mois,
-- drapeau `fiable` aligné sur le seuil, quartiles ordonnés, prix plausibles.
-- Le test échoue s'il retourne des lignes.

select *
from {{ ref('mart_prix_m2_par_quartier') }}
where (nb_ventes_24m < {{ var('seuil_ventes_affichage') }}
       and (prix_m2_median is not null or prix_m2_p25 is not null or prix_m2_p75 is not null
            or evolution_1an_pct is not null or evolution_3ans_pct is not null
            or ecart_commune_pct is not null or prix_median is not null
            or surface_mediane is not null))
   or prix_m2_median_commune < 500
   or (nb_ventes_24m >= {{ var('seuil_ventes_affichage') }} and prix_m2_median is null)
   or fiable <> (nb_ventes_24m >= {{ var('seuil_ventes_fiable') }})
   or prix_m2_p25 > prix_m2_median
   or prix_m2_median > prix_m2_p75
   or prix_m2_median not between 500 and 30000
   or nb_ventes_24m > nb_ventes_total
