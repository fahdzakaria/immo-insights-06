-- Les quartiers d'une commune doivent reconstituer ses ventes : jamais plus
-- que la commune (pas de double compte), et au moins 90 % (un rattachement
-- qui perdrait des ventes en masse rendrait les médianes trompeuses).
-- Le seuil relatif ne joue que si plus de 5 ventes manquent : sur 18 ventes,
-- 2 ventes non géolocalisées (89 %) ne sont pas une perte « en masse ».
-- Le test échoue s'il retourne des lignes.

with quartiers as (
    select code_commune, type_bien, sum(nb_ventes_24m) as nb_quartiers
    from {{ ref('mart_prix_m2_par_quartier') }}
    group by code_commune, type_bien
)

select q.*, c.nb_ventes_24m as nb_commune
from quartiers q
left join {{ ref('mart_prix_m2_par_commune') }} c using (code_commune, type_bien)
where q.nb_quartiers > coalesce(c.nb_ventes_24m, 0)
   or (q.nb_quartiers < 0.9 * coalesce(c.nb_ventes_24m, 0)
       and coalesce(c.nb_ventes_24m, 0) - q.nb_quartiers > 5)
