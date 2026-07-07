#!/usr/bin/env bash
# Déploie l'API sur un Hugging Face Space (Docker).
#
# Prérequis (une fois) :
#   pip install -U "huggingface_hub[cli]"
#   hf auth login          # token "write" créé sur https://huggingface.co/settings/tokens
#
# Usage : ./scripts/deploy_api_hf.sh <utilisateur_hf> [nom_du_space]
set -euo pipefail

HF_USER="${1:?Usage: $0 <utilisateur_hf> [nom_du_space]}"
SPACE="${2:-immo-insights-api}"
REPO="$HF_USER/$SPACE"
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
CONTEXTE="$(mktemp -d)/space"

echo "→ Assemblage du contexte dans $CONTEXTE"
mkdir -p "$CONTEXTE"
cp "$RACINE/api/Dockerfile.deploy" "$CONTEXTE/Dockerfile"
cp "$RACINE/api/requirements.txt" "$CONTEXTE/"
cp -R "$RACINE/api/app" "$CONTEXTE/app"
cp -R "$RACINE/data/gold" "$CONTEXTE/gold"

# Front-matter obligatoire des Spaces (SDK docker + port)
cat > "$CONTEXTE/README.md" <<'EOF'
---
title: Immo Insights API
emoji: 🏠
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Marché immobilier des Alpes-Maritimes — API FastAPI/DuckDB
---

# Immo Insights API

API du projet **Immo Insights N°06** : 128 600 ventes DVF nettoyées et
agrégées en marts (dbt + DuckDB), servies par FastAPI.
Docs interactives : `/docs`. Frontend : voir le repo du projet.
EOF

echo "→ Création du Space (no-op s'il existe) et push"
hf repo create "$REPO" --repo-type space 2>/dev/null || true
hf upload "$REPO" "$CONTEXTE" . --repo-type space --commit-message "deploy $(date -u +%Y-%m-%dT%H:%M)"

echo "✔ Déployé : https://huggingface.co/spaces/$REPO"
echo "  API : https://${HF_USER//_/-}-${SPACE}.hf.space  (build ~2 min au premier déploiement)"
