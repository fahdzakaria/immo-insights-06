"""Tests de l'export JSON des marts gold pour le front statique (hors-ligne)."""

import json

import numpy as np
import pandas as pd
import pytest

from pipelines import export_front


def _gold(tmp_path, vide=None, absent=None):
    """Écrit 5 mini marts gold en Parquet ; `vide`/`absent` cassent un mart."""
    gold = tmp_path / "gold"
    gold.mkdir(parents=True)
    for mart in export_front.MARTS:
        if mart == absent:
            continue
        df = pd.DataFrame({
            "code_commune": ["06088", "06029"],
            "trimestre": ["2025Q4", "2021Q1"],
            "prix_m2_median": [4808.0, np.nan],     # NaN → null
            "latitude": [43.70000000000001, 43.55], # bruit flottant → arrondi
            "nb_ventes": [13744, 4556],
        })
        (df.iloc[0:0] if mart == vide else df).to_parquet(gold / f"{mart}.parquet", index=False)
    return gold


def test_export_ecrit_un_json_par_mart_et_meta(tmp_path):
    out = export_front.exporter(_gold(tmp_path), tmp_path / "front")
    for mart in export_front.MARTS:
        table = json.loads((out / f"{mart}.json").read_text())
        assert table["colonnes"] == ["code_commune", "trimestre", "prix_m2_median", "latitude", "nb_ventes"]
        assert len(table["lignes"]) == 2
    meta = json.loads((out / "meta.json").read_text())
    assert meta["premier_trimestre"] == "2021Q1" and meta["dernier_trimestre"] == "2025Q4"
    assert meta["lignes"]["mart_prix_m2_par_commune"] == 2
    assert meta["genere_le"].endswith("+00:00")
    assert not list(out.glob("*.tmp"))  # écritures atomiques : aucun résidu


def test_export_json_strict_et_stable(tmp_path):
    out = export_front.exporter(_gold(tmp_path), tmp_path / "front")
    brut = (out / "mart_impact_dpe.json").read_text()
    assert "NaN" not in brut
    lignes = json.loads(brut)["lignes"]
    # Trié (diff git stable) : 06029 avant 06088 ; codes gardés en texte
    assert [l[0] for l in lignes] == ["06029", "06088"]
    assert lignes[0][2] is None            # NaN → null
    assert lignes[1][2] == 4808            # 4808.0 → 4808
    assert lignes[1][3] == 43.7            # bruit flottant gommé
    # Deux exports de la même donnée → fichiers identiques
    export_front.exporter(tmp_path / "gold", tmp_path / "front2")
    assert brut == (tmp_path / "front2" / "mart_impact_dpe.json").read_text()


def test_mart_absent_ou_vide_annule_tout_l_export(tmp_path):
    """On ne publie jamais un site à moitié vide : rien n'est écrit."""
    with pytest.raises(FileNotFoundError):
        export_front.exporter(_gold(tmp_path / "a", absent="mart_impact_dpe"), tmp_path / "front_a")
    with pytest.raises(ValueError, match="vide"):
        export_front.exporter(_gold(tmp_path / "b", vide="mart_score_investissement"), tmp_path / "front_b")
    assert not list((tmp_path / "front_a").glob("*.json"))
    assert not list((tmp_path / "front_b").glob("*.json"))


def test_donnee_inchangee_ne_reecrit_rien(tmp_path):
    """Même donnée → meta.json (date du pied de page) et fichiers intacts."""
    gold = _gold(tmp_path)
    out = export_front.exporter(gold, tmp_path / "front")
    meta_avant = (out / "meta.json").read_text()
    (out / "meta.json").write_text(meta_avant.replace("2025Q4", "MARQUEUR"))
    export_front.exporter(gold, out)
    assert "MARQUEUR" in (out / "meta.json").read_text()  # pas réécrit
    # Une donnée qui change → tout est réécrit, meta compris
    df = pd.read_parquet(gold / "mart_impact_dpe.parquet")
    df.loc[0, "nb_ventes"] = 1
    df.to_parquet(gold / "mart_impact_dpe.parquet", index=False)
    export_front.exporter(gold, out)
    assert "MARQUEUR" not in (out / "meta.json").read_text()


def test_bruit_flottant_ne_compte_pas_comme_un_changement(tmp_path):
    """Une latitude qui bouge de 0,000001 (bruit d'agrégation) ne réécrit rien ;
    un vrai changement, même petit (0,01 point de %), si."""
    gold = _gold(tmp_path)
    out = export_front.exporter(gold, tmp_path / "front")
    meta = out / "meta.json"
    meta.write_text(meta.read_text().replace("2025Q4", "MARQUEUR"))

    def modifier(colonne, valeur):
        df = pd.read_parquet(gold / "mart_impact_dpe.parquet")
        df.loc[0, colonne] = valeur
        df.to_parquet(gold / "mart_impact_dpe.parquet", index=False)

    modifier("latitude", 43.700001)          # +0,000001 : bruit
    export_front.exporter(gold, out)
    assert "MARQUEUR" in meta.read_text()

    modifier("latitude", 43.70001)           # +0,00001 : vrai déplacement
    export_front.exporter(gold, out)
    assert "MARQUEUR" not in meta.read_text()


def test_changement_de_texte_ou_de_null_detecte(tmp_path):
    gold = _gold(tmp_path)
    out = export_front.exporter(gold, tmp_path / "front")
    table = export_front.lire_mart(gold / "mart_impact_dpe.parquet")
    assert export_front._meme_donnee(out / "mart_impact_dpe.json", table)
    table["lignes"][0][0] = "06030"                      # un code commune change
    assert not export_front._meme_donnee(out / "mart_impact_dpe.json", table)
    table = export_front.lire_mart(gold / "mart_impact_dpe.parquet")
    table["lignes"][0][2] = 4000                         # null → valeur
    assert not export_front._meme_donnee(out / "mart_impact_dpe.json", table)
    assert not export_front._meme_donnee(out / "absent.json", table)
