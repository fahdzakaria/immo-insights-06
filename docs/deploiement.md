# Déploiement

- Site : https://immo-insights-06.vercel.app (projet Vercel `immo-insights-06`, scope `fahdzakarias-projects`)
- API (historique) : https://fahedza-immo-insights-api.hf.space/docs (Space `fahedza/immo-insights-api`)

## Architecture en ligne : site statique, marts embarqués

```
DAG Airflow (local)                         Vercel
  … → dbt run → dbt test → export_json_front ──►  frontend/public/data/*.json
                                                  + lib/local-api.ts (filtrage dans le navigateur)
```

Les 5 marts gold pèsent ~150 Ko en Parquet (~570 Ko en JSON, ~90 Ko une fois
compressés par Vercel). Le site les embarque et rejoue dans le navigateur la
logique des endpoints de l'API (`frontend/lib/local-api.ts`) : **aucun serveur
à héberger, aucun temps de réveil, aucun point de panne**.

Ce choix date de novembre 2026 : Hugging Face a rendu payants les Spaces
Docker gratuits, donc l'API ne pouvait plus être republiée. L'API FastAPI
reste dans le projet et dans le stack Docker local (`docker compose up`), où
le site l'interroge (`NEXT_PUBLIC_DATA_SOURCE=api`).

| Variable (au build du front) | Valeur | Effet |
| --- | --- | --- |
| `NEXT_PUBLIC_DATA_SOURCE` | `static` (défaut) | marts JSON embarqués, pas d'API |
| | `api` | le site appelle `NEXT_PUBLIC_API_URL` (stack Docker) |

## Publier des données fraîches

1. Le DAG `immo_pipeline` termine par la tâche `export_json_front`, qui
   réécrit `frontend/public/data/` **seulement si les tests dbt passent**.
   À la main : `make export-front`.
2. Redéployer le site :

```bash
make publier
# équivaut à : cd frontend && npx vercel deploy --prod --yes --scope fahdzakarias-projects
```

Prérequis une seule fois : `npx vercel login`. Le pied de page du site affiche
la date réelle du dernier export (`public/data/meta.json`).

## Vérifier que le site statique répond comme l'API

```bash
docker compose up -d            # l'API locale sert les mêmes marts gold
make export-front
cd frontend && node scripts/compare-local-api.ts
# ✔ 1798 requêtes identiques entre l'API et la version locale
```

Le script rejoue toutes les vues du site (tous les filtres, toutes les
communes, toutes les estimations) contre l'API et contre la version locale,
et échoue à la moindre différence. À relancer après toute modification d'un
endpoint ou de `lib/local-api.ts`.

## API sur Hugging Face (historique)

`scripts/deploy_api_hf.sh <pseudo>` assemble un contexte Docker (API + marts
gold) et le pousse sur un Space. Depuis novembre 2026 la commande échoue avec
une erreur 402 sans abonnement PRO ; le Space existant continue de tourner
avec les données du 7 juillet 2026. Le script fonctionne tel quel sur tout
hébergeur Docker (`api/Dockerfile.deploy`).
