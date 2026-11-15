# Déploiement

- Site : https://immo-insights-06.vercel.app (projet Vercel `immo-insights-06`, scope `fahdzakarias-projects`)
- API (historique) : https://fahedza-immo-insights-api.hf.space/docs (Space `fahedza/immo-insights-api`)

## Architecture en ligne : site statique, marts embarqués

```
DAG Airflow (local)                         Vercel
  … → dbt run → dbt test → export_json_front ──►  frontend/public/data/*.json
                                                  + lib/local-api.ts (filtrage dans le navigateur)
```

Les 6 marts gold pèsent ~700 Ko en JSON (~120 Ko une fois compressés par
Vercel), dont 123 Ko pour les quartiers. Les contours des quartiers IRIS
(`public/geo/iris-06.geojson`, 778 Ko, ~170 Ko compressés) sont un fichier à
part, téléchargé seulement quand on zoome sur la carte. Le site les embarque et rejoue dans le navigateur la
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

## Publication automatique (GitHub Actions)

Le workflow `.github/workflows/publication.yml` publie le site sans dépendre
d'un ordinateur allumé :

| Déclencheur | Ce qui se passe |
| --- | --- |
| Chaque lundi matin (04:17 UTC) | pipeline complet à partir de zéro (`scripts/pipeline_complet.sh` : sources publiques → silver → marts dbt + tests → export JSON) ; si la donnée a changé, commit des JSON sur `main` puis publication |
| Push sur `main` touchant `frontend/` | publication du site |
| Manuel (onglet Actions → Publication → Run workflow) | comme le lundi ; une case permet de publier même sans changement de donnée |

Si une source est indisponible ou qu'un test dbt échoue, le job s'arrête :
rien n'est commité, l'ancien site reste en ligne, et GitHub prévient par
e-mail. La donnée est jugée « changée » au bruit flottant près
(`pipelines/export_front.py`), donc pas de commit ni de déploiement inutiles.
L'export écrit aussi les contours des quartiers IRIS dans `geo/`, à côté du
dossier des JSON : le workflow monte donc tout `frontend/public` dans le
conteneur et commite `frontend/public/data` **et** `frontend/public/geo`
(les contours ne changent qu'avec le millésime IRIS, une fois par an).

Secrets à définir une fois (Settings → Secrets and variables → Actions) :

```bash
gh secret set VERCEL_TOKEN        # jeton créé sur https://vercel.com/account/tokens
gh secret set VERCEL_ORG_ID       # champ orgId de frontend/.vercel/project.json
gh secret set VERCEL_PROJECT_ID   # champ projectId du même fichier
```

Le stack Docker local (DAG Airflow quotidien) reste l'environnement de
développement : il exporte ses JSON dans `data/front` (et les contours dans
`data/geo`), non versionnés, pour ne pas modifier le dépôt à chaque run.

## Publication manuelle (secours)

```bash
make export-front   # écrit frontend/public/data depuis les marts locaux
make publier        # export + npx vercel deploy --prod (demande `npx vercel login`)
```

Le pied de page du site affiche la date réelle du dernier export
(`public/data/meta.json`).

## Vérifier que le site statique répond comme l'API

```bash
docker compose up -d            # l'API locale sert les mêmes marts gold
make export-front
cd frontend && node scripts/compare-local-api.ts
# ✔ 2810 requêtes identiques entre l'API et la version locale
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
