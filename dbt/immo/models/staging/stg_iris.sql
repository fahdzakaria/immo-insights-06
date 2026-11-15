-- Référentiel des quartiers IRIS (contours IGN/INSEE ingérés en bronze).
-- Pas de géométrie ici : le point-dans-polygone est fait en silver, les
-- marts n'ont besoin que des codes et des noms.
-- `nb_iris_commune` > 1 = commune découpée en quartiers par l'INSEE ; les
-- autres forment un seul IRIS (type « Z ») identique à la commune.

select
    code_iris,
    nom_iris,
    type_iris,
    code_commune,
    nom_commune,
    count(*) over (partition by code_commune) as nb_iris_commune
from {{ source('bronze', 'iris_contours') }}
