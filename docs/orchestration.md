# Orchestration Airflow

## Le DAG `immo_pipeline`

```
bronze.dvf ─────────────► silver.dvf ──────────┐
bronze.dpe ─────────────► silver.dpe ──────────┤
bronze.osm ─────────────► silver.osm ──────────┼─► silver.enrichissement ─► dbt_run ─► dbt_test ─► dbt_docs
bronze.insee ──┬────────► silver.referentiels ─┘
bronze.loyers ─┘
```

- **Dépendances fines** : chaque nettoyage silver n'attend que *sa* source
  bronze — l'échec d'OSM ne bloque pas le nettoyage DVF, seul
  l'enrichissement (qui a besoin de tout) attend.
- **Planification** : tous les jours à 06:00 Europe/Paris, `catchup=False`
  (chaque run reconstruit l'état courant, pas d'historique à rattraper).
- **Relançable sans danger** : le bronze saute les sources déjà ingérées
  (manifestes), silver et dbt sont déterministes.

## Garde-fous opérationnels (tous testés dans tests/test_dags.py)

| Garde-fou | Valeur | Pourquoi |
| --- | --- | --- |
| `retries` | 2, backoff exponentiel, 5 min | les APIs publiques (Overpass, ADEME) tombent transitoirement |
| `max_active_runs` | 1 | DuckDB n'accepte qu'un écrivain à la fois |
| `on_failure_callback` | log + webhook / Telegram | voir alerting ci-dessous |
| `dbt_test` bloquant | après `dbt_run` | des marts qui échouent aux tests qualité ne doivent pas passer inaperçus |

## Alerting

Chaque échec de tâche (après épuisement des retries) déclenche
`alerte_echec`, qui délègue à `pipelines/alertes.py` : log ERROR, puis envoi
sur chaque canal configuré, avec la tâche, le run, la tentative et l'URL du
log. Deux canaux, à configurer dans `.env` (aucun n'est obligatoire) :

```bash
# Webhook entrant Slack ou Discord
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
# Bot Telegram (créé avec @BotFather) : les deux variables sont nécessaires
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Après modification de `.env` : `docker compose up -d` (recrée les conteneurs
Airflow), puis `make test-alerte` envoie un message de test et indique les
canaux qui ont répondu. Une alerte qui échoue ne fait jamais échouer le
pipeline, et le jeton du bot n'est jamais écrit dans les logs.

## Lancer / tester

```bash
# Exécution complète immédiate (sans scheduler) — c'est le test de bout en bout
docker compose exec airflow-scheduler airflow dags test immo_pipeline

# Activer la planification quotidienne (ou via le toggle de l'UI)
docker compose exec airflow-scheduler airflow dags unpause immo_pipeline

# UI : http://localhost:8081 (admin/admin) → DAG immo_pipeline → Graph
```

Les DAGs sont créés **en pause** (`AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION`)
pour garder la main sur le premier déclenchement.
