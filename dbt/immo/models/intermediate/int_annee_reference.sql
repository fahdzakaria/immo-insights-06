-- Année de référence des marts = dernière année COMPLÈTE de ventes.
-- DVF est publié par semestre : quand le 1er semestre de l'année N arrive,
-- max(annee) passerait à N et les fenêtres « 24 mois » ou les évolutions
-- annuelles compareraient 6 mois à 12. On prend donc la dernière année qui
-- contient des ventes en décembre (repli : la dernière année présente).
-- Les trimestres de l'année en cours restent visibles dans
-- mart_evolution_trimestrielle.

select
    coalesce(
        max(annee) filter (where month(date_mutation) = 12),
        max(annee)
    ) as annee_courante
from {{ ref('stg_ventes') }}
