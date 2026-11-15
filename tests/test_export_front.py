"""Tests de l'export JSON des marts gold pour le front statique (hors-ligne)."""

import json

import numpy as np
import pandas as pd
import pytest

from pipelines import export_front


QUARTIER = "mart_prix_m2_par_quartier"
COLONNES = ["code_commune", "trimestre", "prix_m2_median", "latitude", "nb_ventes"]


def _contour(code, lon0=7.26):
    """Un carré de ~1 km, avec du bruit après la 5e décimale et un sommet en double."""
    return {"code_iris": code, "nom_iris": f"Quartier {code[-2:]}", "code_commune": code[:5],
            "nom_commune": "Nice" if code.startswith("06088") else "Cannes",
            "type_iris": "H", "id_ign": None,
            "geometrie_geojson": json.dumps({"type": "Polygon", "coordinates": [[
                [lon0, 43.70], [lon0 + 0.0100004, 43.70], [lon0 + 0.0100001, 43.7000002],
                [lon0 + 0.01, 43.71], [lon0, 43.71], [lon0, 43.70]]]})}


@pytest.fixture(autouse=True)
def bronze(tmp_path, monkeypatch):
    """Contours IRIS bronze synthétiques : 2 quartiers du mart + 1 hors mart."""
    dossier = tmp_path / "bronze" / "iris" / "departement=06"
    dossier.mkdir(parents=True)
    pd.DataFrame([_contour("060880101"), _contour("060290101", 7.02), _contour("069990101", 7.50)]
                 ).to_parquet(dossier / "contours.parquet", index=False)
    monkeypatch.setattr(export_front, "BRONZE_DIR", tmp_path / "bronze")
    return tmp_path / "bronze"


def _gold(tmp_path, vide=None, absent=None):
    """Écrit 6 mini marts gold en Parquet ; `vide`/`absent` cassent un mart."""
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
        if mart == QUARTIER:  # l'export des contours lit ces deux colonnes
            df = df.assign(code_iris=["060880101", "060290101"], code_departement="06")
        (df.iloc[0:0] if mart == vide else df).to_parquet(gold / f"{mart}.parquet", index=False)
    return gold


def test_export_ecrit_un_json_par_mart_et_meta(tmp_path):
    out = export_front.exporter(_gold(tmp_path), tmp_path / "front")
    for mart in export_front.MARTS:
        table = json.loads((out / f"{mart}.json").read_text())
        assert table["colonnes"][:5] == COLONNES
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


# --- Contours des quartiers (public/geo/iris-{dep}.geojson) ---

def test_contours_exportes_pour_les_seuls_quartiers_du_mart(tmp_path):
    out = export_front.exporter(_gold(tmp_path), tmp_path / "front")
    geo = json.loads((out.parent / "geo" / "iris-06.geojson").read_text())
    assert geo["type"] == "FeatureCollection"
    assert [f["properties"]["code"] for f in geo["features"]] == ["060290101", "060880101"]  # trié, 06999 exclu
    assert geo["features"][1]["properties"] == {
        "code": "060880101", "nom": "Quartier 01", "commune": "06088", "nom_commune": "Nice"}


def test_contours_alleges_arrondis_sans_doublon():
    geometrie = json.loads(_contour("060880101")["geometrie_geojson"])
    anneau = export_front.alleger_geometrie(geometrie)["coordinates"][0]
    # 5 décimales, et les deux sommets confondus après arrondi n'en font plus qu'un
    assert anneau == [[7.26, 43.7], [7.27, 43.7], [7.27, 43.71], [7.26, 43.71], [7.26, 43.7]]
    multi = {"type": "MultiPolygon", "coordinates": [
        geometrie["coordinates"],
        [[[7.3, 43.7], [7.3000001, 43.7], [7.3, 43.7000001], [7.3, 43.7]]],  # éclat < 1 m : disparaît
    ]}
    assert len(export_front.alleger_geometrie(multi)["coordinates"]) == 1


def test_contour_exterieur_degenere_supprime_avec_ses_trous():
    """Un éclat dont l'extérieur disparaît ne doit pas laisser son trou devenir un faux polygone."""
    vrai = json.loads(_contour("060880101")["geometrie_geojson"])["coordinates"]
    eclat = [
        [[7.4, 43.7], [7.4000001, 43.7], [7.4, 43.7000001], [7.4, 43.7]],          # extérieur < 1 m
        [[7.41, 43.71], [7.42, 43.71], [7.42, 43.72], [7.41, 43.72], [7.41, 43.71]],  # « trou » de 1 km
    ]
    out = export_front.alleger_geometrie({"type": "MultiPolygon", "coordinates": [vrai, eclat]})
    assert len(out["coordinates"]) == 1 and out["coordinates"][0][0][0] == [7.26, 43.7]
    # Trou dégénéré dans un vrai polygone : seul le trou disparaît
    avec_trou = vrai + [[[7.262, 43.702], [7.2620001, 43.702], [7.262, 43.7020001], [7.262, 43.702]]]
    assert len(export_front.alleger_geometrie({"type": "Polygon", "coordinates": avec_trou})["coordinates"]) == 1
    with pytest.raises(ValueError, match="vide"):
        export_front.alleger_geometrie({"type": "Polygon", "coordinates": eclat[:1]})


def test_quartier_du_mart_sans_contour_annule_l_export(tmp_path):
    gold = _gold(tmp_path)
    df = pd.read_parquet(gold / f"{QUARTIER}.parquet")
    df.loc[0, "code_iris"] = "060889999"
    df.to_parquet(gold / f"{QUARTIER}.parquet", index=False)
    with pytest.raises(ValueError, match="sans contour"):
        export_front.exporter(gold, tmp_path / "front")
    assert not list((tmp_path / "front").glob("*.json"))


def test_contours_bronze_absents_annule_l_export(tmp_path):
    with pytest.raises(FileNotFoundError, match="Contours IRIS absents"):
        export_front.exporter(_gold(tmp_path), tmp_path / "front", bronze_dir=tmp_path / "vide")


def test_contours_identiques_non_reecrits(tmp_path):
    gold = _gold(tmp_path)
    out = export_front.exporter(gold, tmp_path / "front")
    fichier = out.parent / "geo" / "iris-06.geojson"
    avant = fichier.stat().st_mtime_ns
    export_front.exporter(gold, out)
    assert fichier.stat().st_mtime_ns == avant
    assert not list(fichier.parent.glob("*.tmp"))


def test_chute_brutale_du_nombre_de_lignes_refusee(tmp_path, monkeypatch):
    """Publication automatique : un mart qui passe de 2 à 1 ligne (−50 %) est refusé,
    sauf si on l'accepte explicitement."""
    monkeypatch.delenv("EXPORT_ACCEPTER_BAISSE", raising=False)
    gold = _gold(tmp_path)
    out = export_front.exporter(gold, tmp_path / "front")
    df = pd.read_parquet(gold / "mart_impact_dpe.parquet").iloc[:1]
    df.to_parquet(gold / "mart_impact_dpe.parquet", index=False)
    with pytest.raises(ValueError, match="tronquée"):
        export_front.exporter(gold, out)
    assert len(json.loads((out / "mart_impact_dpe.json").read_text())["lignes"]) == 2  # rien n'a bougé
    monkeypatch.setenv("EXPORT_ACCEPTER_BAISSE", "1")
    export_front.exporter(gold, out)
    assert len(json.loads((out / "mart_impact_dpe.json").read_text())["lignes"]) == 1
