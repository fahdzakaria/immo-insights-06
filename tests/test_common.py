"""Tests du socle commun : écriture atomique, manifestes, idempotence, CSV flexibles."""

import pandas as pd
import pytest

from pipelines.common import already_ingested, atomic_write_parquet, read_csv_flexible, write_manifest


@pytest.fixture
def df():
    return pd.DataFrame({"code_commune": ["06004", "06029"], "valeur": [1.5, 2.0]})


def test_atomic_write_parquet_roundtrip(tmp_path, df):
    out = tmp_path / "sub" / "test.parquet"
    atomic_write_parquet(df, out)
    assert out.exists()
    assert not out.with_suffix(".parquet.tmp").exists(), "le fichier temporaire doit être renommé"
    pd.testing.assert_frame_equal(pd.read_parquet(out), df)


def test_idempotence_skip_et_force(tmp_path, df):
    out = tmp_path / "test.parquet"
    url = "https://example.org/source.csv"

    # Jamais ingéré → on n'est pas censé sauter
    assert not already_ingested(out, source=url)

    atomic_write_parquet(df, out)
    write_manifest(out, source=url, rows=len(df))

    # Même source déjà ingérée → skip
    assert already_ingested(out, source=url)
    # Source différente (ex : nouveau millésime) → on ré-ingère
    assert not already_ingested(out, source="https://example.org/autre.csv")
    # --force → on ré-ingère toujours
    assert not already_ingested(out, source=url, force=True)


def test_politique_de_fraicheur(tmp_path, df):
    """Les sources publiques changent sous des URLs stables : au-delà de
    max_age_jours, on doit re-télécharger même si la source est identique."""
    import json
    from datetime import datetime, timedelta, timezone

    out = tmp_path / "test.parquet"
    url = "https://example.org/source.csv"
    atomic_write_parquet(df, out)
    write_manifest(out, source=url, rows=len(df))

    # Fraîche → skip ; sans limite d'âge → skip
    assert already_ingested(out, source=url, max_age_jours=7)
    assert already_ingested(out, source=url)

    # On vieillit artificiellement le manifeste de 10 jours
    mpath = out.with_suffix(".manifest.json")
    manifest = json.loads(mpath.read_text())
    manifest["ingested_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    mpath.write_text(json.dumps(manifest))

    assert not already_ingested(out, source=url, max_age_jours=7), "périmée → re-télécharger"
    assert already_ingested(out, source=url, max_age_jours=30), "encore fraîche pour un TTL de 30 j"

    # Manifeste sans date exploitable → re-télécharger par prudence
    del manifest["ingested_at"]
    mpath.write_text(json.dumps(manifest))
    assert not already_ingested(out, source=url, max_age_jours=7)


def test_parquet_sans_manifest_est_reingere(tmp_path, df):
    out = tmp_path / "test.parquet"
    atomic_write_parquet(df, out)  # pas de manifeste écrit
    assert not already_ingested(out, source="https://example.org/source.csv")


def test_read_csv_flexible_point_virgule():
    payload = "CODGEO;LIBGEO\n06004;Antibes\n".encode("utf-8")
    df = read_csv_flexible(payload, dtype="string")
    assert list(df.columns) == ["CODGEO", "LIBGEO"]
    assert df.loc[0, "CODGEO"] == "06004", "les zéros de tête doivent être préservés"


def test_read_csv_flexible_virgule_et_latin1():
    payload = "commune,loyer\nNice côte d'azur,15.2\n".encode("latin-1")
    df = read_csv_flexible(payload)
    assert list(df.columns) == ["commune", "loyer"]
    assert "côte" in df.loc[0, "commune"]
