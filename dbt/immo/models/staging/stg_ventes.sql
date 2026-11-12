-- Vue de staging : typage/sélection au-dessus du Parquet silver.
-- Aucune logique métier ici : le nettoyage vit en silver (Python),
-- les agrégations en marts.

select
    id_mutation                  as vente_id,
    date_mutation,
    annee,
    trimestre,
    type_bien,
    valeur_fonciere,
    surface_bati,
    prix_m2,
    nb_pieces,
    code_commune,
    nom_commune,
    code_departement,
    latitude,
    longitude,
    geocode_source,
    -- contexte communal (déjà joint en silver)
    population,
    evolution_population_pct,
    niveau_vie_median,
    taux_pauvrete,
    taux_logements_vacants,
    taux_residences_secondaires,
    loyer_m2_ref,
    -- accessibilité
    nb_education_500m,
    nb_transport_500m,
    nb_commerce_500m,
    -- DPE rapproché
    etiquette_dpe,
    etiquette_ges,
    conso_ep_m2,
    dpe_distance_m,
    dpe_nb_candidats,
    dpe_ambigu
from {{ source('silver', 'ventes_enrichies') }}
