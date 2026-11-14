"""Tests des alertes d'échec (hors-ligne : requests.post est simulé)."""

import logging

import pytest
import requests

from pipelines import alertes


class _Reponse:
    def __init__(self, statut=200):
        self.status_code = statut

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def envois(monkeypatch):
    """Capture les appels à requests.post et vide la configuration d'alerte."""
    for var in ("ALERT_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)
    appels = []

    def faux_post(url, json=None, timeout=None):
        appels.append({"url": url, "json": json, "timeout": timeout})
        return _Reponse()

    monkeypatch.setattr(alertes.requests, "post", faux_post)
    return appels


def test_sans_configuration_rien_n_est_envoye(envois):
    assert alertes.canaux_configures() == []
    assert alertes.envoyer_alerte("échec") == []
    assert envois == []


def test_telegram(envois, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:JETON")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert alertes.envoyer_alerte("❌ échec de bronze.dpe") == ["telegram"]
    assert envois[0]["url"] == "https://api.telegram.org/bot123:JETON/sendMessage"
    assert envois[0]["json"]["chat_id"] == "42"
    assert envois[0]["json"]["text"] == "❌ échec de bronze.dpe"
    assert envois[0]["timeout"] == alertes.DELAI_S


def test_telegram_incomplet_ignore(envois, monkeypatch):
    """Jeton sans identifiant de conversation : canal inactif, pas d'appel."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:JETON")
    assert alertes.canaux_configures() == []
    assert alertes.envoyer_alerte("échec") == []
    assert envois == []


def test_webhook_et_telegram_ensemble(envois, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.exemple.test/abc")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:JETON")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert alertes.envoyer_alerte("échec") == ["webhook", "telegram"]
    assert envois[0]["json"] == {"text": "échec", "content": "échec"}  # Slack ET Discord


def test_echec_d_envoi_n_explose_pas_et_ne_divulgue_pas_le_jeton(monkeypatch, caplog):
    """Une alerte qui échoue ne doit ni lever, ni écrire le jeton du bot dans les logs."""
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:JETON-SECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def post_en_panne(url, json=None, timeout=None):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(alertes.requests, "post", post_en_panne)
    with caplog.at_level(logging.ERROR):
        assert alertes.envoyer_alerte("échec") == []
    assert "JETON-SECRET" not in caplog.text
    assert "Telegram impossible" in caplog.text


def test_reponse_http_en_erreur_non_comptee(envois, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.exemple.test/abc")
    monkeypatch.setattr(alertes.requests, "post", lambda url, json=None, timeout=None: _Reponse(404))
    assert alertes.envoyer_alerte("échec") == []


def test_exception_inattendue_n_explose_pas(monkeypatch, caplog):
    """Même une erreur qui n'est pas réseau (jeton mal formé…) reste contenue et muette sur le jeton."""
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:JETON-SECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def post_casse(url, json=None, timeout=None):
        raise ValueError(f"URL invalide : {url}")

    monkeypatch.setattr(alertes.requests, "post", post_casse)
    with caplog.at_level(logging.DEBUG):
        assert alertes.envoyer_alerte("échec") == []
    assert "JETON-SECRET" not in caplog.text
