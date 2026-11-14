"""Alertes d'échec du pipeline : webhook Slack/Discord et/ou Telegram.

Configuration par variables d'environnement (toutes optionnelles) :
  - ALERT_WEBHOOK_URL                     : webhook entrant Slack ou Discord ;
  - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID : message via un bot Telegram.
Sans configuration, l'alerte est seulement journalisée (niveau ERROR).

Une alerte qui échoue ne doit jamais faire échouer le pipeline une seconde
fois : toutes les erreurs d'envoi sont attrapées et journalisées.
"""

import logging
import os

import requests

logger = logging.getLogger("alertes")
# urllib3 écrit le chemin de chaque requête en DEBUG — or le jeton Telegram est dans ce chemin
logging.getLogger("urllib3").setLevel(logging.WARNING)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
DELAI_S = 10


def canaux_configures() -> list[str]:
    """Canaux d'alerte actifs, pour les logs et les tests."""
    canaux = []
    if os.environ.get("ALERT_WEBHOOK_URL"):
        canaux.append("webhook")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        canaux.append("telegram")
    return canaux


def envoyer_alerte(message: str) -> list[str]:
    """Envoie `message` sur chaque canal configuré ; retourne les canaux qui ont réussi."""
    logger.error(message)
    reussis: list[str] = []

    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            # "text" pour Slack, "content" pour Discord
            reponse = requests.post(webhook, json={"text": message, "content": message}, timeout=DELAI_S)
            reponse.raise_for_status()
            reussis.append("webhook")
        except Exception as exc:  # noqa: BLE001 — une alerte ne doit jamais faire planter le callback
            logger.error("Envoi de l'alerte webhook impossible (%s)", type(exc).__name__)

    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            reponse = requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
                timeout=DELAI_S,
            )
            reponse.raise_for_status()
            reussis.append("telegram")
        except Exception as exc:  # noqa: BLE001 — idem, et une exception non attrapée afficherait l'URL
            # Ne JAMAIS journaliser l'exception entière : son texte contient l'URL, donc le jeton du bot
            logger.error("Envoi de l'alerte Telegram impossible (%s)", type(exc).__name__)

    if not canaux_configures():
        logger.warning("Aucun canal d'alerte configuré (ALERT_WEBHOOK_URL ou TELEGRAM_*) : alerte seulement journalisée")
    return reussis


if __name__ == "__main__":
    # Test manuel : python -m pipelines.alertes
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    envoyes = envoyer_alerte("✅ Pipeline immo : test d'alerte (aucun échec, simple vérification du canal)")
    print("Canaux configurés :", canaux_configures() or "aucun", "| envoyés :", envoyes or "aucun")
