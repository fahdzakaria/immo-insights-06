# Déploiement

**URLs de production :**
- Frontend : https://immo-insights-06.vercel.app (projet Vercel `immo-insights-06`, scope `fahdzakarias-projects`)
- API : https://fahedza-immo-insights-api.hf.space/docs (Space `fahedza/immo-insights-api`)

## Architecture en ligne

```
Vercel (frontend Next.js)  ──fetch──►  Hugging Face Space (API FastAPI, Docker)
                                        └── marts gold Parquet EMBARQUÉS (~150 Ko)
```

**Parti pris** : les marts sont si compacts qu'ils sont copiés dans l'image
Docker de l'API ([api/Dockerfile.deploy](../api/Dockerfile.deploy)). Aucune
base de données à héberger, aucun secret, cold-start instantané. Publier des
données fraîches = relancer le script de déploiement (qui reprend le contenu
de `data/gold/` produit par le DAG local).

## 1. API → Hugging Face Spaces (gratuit, sans CB)

Prérequis une seule fois :
1. Compte sur https://huggingface.co/join
2. Token **write** : https://huggingface.co/settings/tokens
3. `hf auth login` (coller le token)

Déploiement (et re-déploiements suivants) :

```bash
./scripts/deploy_api_hf.sh <ton_pseudo_hf>
# → https://<pseudo>-immo-insights-api.hf.space/docs
```

Le script assemble un contexte (Dockerfile + app + gold + README à
front-matter Spaces), crée le Space s'il n'existe pas, pousse. Build HF ≈ 2 min.

Limite du plan gratuit : le Space s'endort après ~48 h sans trafic et se
réveille à la première requête (~30 s).

## 2. Frontend → Vercel

Prérequis une seule fois : compte sur https://vercel.com puis `npx vercel login`.

```bash
cd frontend
npx vercel deploy --prod --yes \
  --build-env NEXT_PUBLIC_API_URL=https://<pseudo>-immo-insights-api.hf.space
```

`NEXT_PUBLIC_API_URL` est figée au build (variable publique côté navigateur).
L'API accepte tous les origins en GET (CORS ouvert, lecture seule).

## Mises à jour

| Quoi | Commande |
| --- | --- |
| Données fraîches en ligne | `airflow dags trigger immo_pipeline` (local) puis `./scripts/deploy_api_hf.sh <pseudo>` |
| Nouveau code frontend | `cd frontend && npx vercel deploy --prod --yes --build-env NEXT_PUBLIC_API_URL=…` |
| Nouveau code API | `./scripts/deploy_api_hf.sh <pseudo>` |
