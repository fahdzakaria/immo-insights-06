/**
 * API « locale » : rejoue dans le navigateur les endpoints de l'API FastAPI
 * (api/app/routers/*.py) à partir des marts gold exportés en JSON
 * (public/data/*.json, produits par pipelines/export_front.py).
 *
 * Pourquoi : les marts pèsent ~150 Ko en Parquet (~90 Ko de JSON compressé). Les embarquer supprime l'API à
 * héberger, son temps de réveil et un point de panne. Les pages ne changent
 * pas : elles appellent toujours apiGet("/api/v1/...", params).
 *
 * Chaque fonction reprend la requête SQL de l'endpoint correspondant (mêmes
 * filtres, mêmes tris, NULLS LAST, mêmes arrondis). Ce fichier n'importe rien
 * à l'exécution : scripts/compare-local-api.ts le charge directement avec
 * Node pour comparer ses réponses à celles de la vraie API.
 */

export type Ligne = Record<string, any>;
export type Params = Record<string, string | number | undefined | null>;
export type ChargeurMart = (mart: string) => Promise<Ligne[]>;

/** Erreur portant un statut HTTP, comme le ferait l'API. */
export class ErreurApiLocale extends Error {
  statut: number;

  constructor(statut: number, chemin: string, detail?: string) {
    super(detail ? `API ${statut} sur ${chemin} — ${detail}` : `API ${statut} sur ${chemin}`);
    this.statut = statut;
  }
}

/** Fichier exporté {"colonnes": [...], "lignes": [[...]]} → liste d'objets. */
export function decompacter(table: { colonnes: string[]; lignes: unknown[][] }): Ligne[] {
  return table.lignes.map((l) => Object.fromEntries(table.colonnes.map((c, i) => [c, l[i]])));
}

// ---------- utilitaires reproduisant le comportement SQL (DuckDB) ----------

const present = (v: unknown) => v !== undefined && v !== null && v !== "";

function nombre(v: unknown): number | undefined {
  if (!present(v)) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/** round() SQL : arrondi « half away from zero » (Math.round arrondit -2.5 vers -2). */
function arrondi(x: number | null, decimales = 0): number | null {
  if (x === null || !Number.isFinite(x)) return null;
  const f = 10 ** decimales;
  const r = (Math.sign(x) * Math.round(Math.abs(x) * f)) / f;
  return r === 0 ? 0 : r; // évite -0
}

/** round() de Python (utilisé par l'endpoint estimation) : les .5 vont à l'entier pair. */
function arrondiPython(x: number): number {
  const bas = Math.floor(x);
  const reste = x - bas;
  if (reste !== 0.5) return Math.round(x);
  return bas % 2 === 0 ? bas : bas + 1;
}

/** median() SQL : ignore les NULL, moyenne des deux valeurs centrales si effectif pair. */
function mediane(valeurs: unknown[]): number | null {
  const v = valeurs.filter((x): x is number => typeof x === "number").sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

/** ORDER BY col ASC|DESC NULLS LAST (tri stable). */
function trier(lignes: Ligne[], colonne: string, ordre: "asc" | "desc"): Ligne[] {
  const sens = ordre === "desc" ? -1 : 1;
  return [...lignes].sort((a, b) => {
    const x = a[colonne];
    const y = b[colonne];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return x < y ? -sens : x > y ? sens : 0;
  });
}

function entier(v: unknown, defaut: number, min: number, max: number): number {
  const n = nombre(v);
  return Math.min(max, Math.max(min, n === undefined ? defaut : Math.trunc(n)));
}

/** WHERE col >= borne : une valeur NULL ne passe jamais le filtre, comme en SQL. */
const auMoins = (v: unknown, borne: number | undefined) =>
  borne === undefined || (typeof v === "number" && v >= borne);
const auPlus = (v: unknown, borne: number | undefined) =>
  borne === undefined || (typeof v === "number" && v <= borne);

function choisir<T extends string>(v: unknown, permis: Record<T, string>, defaut: T): T {
  return present(v) && String(v) in permis ? (String(v) as T) : defaut;
}

const TRIS_COMMUNES = {
  prix_m2: "prix_m2_median",
  ventes: "nb_ventes_total",
  evolution: "evolution_1an_pct",
  population: "population",
  nom: "nom_commune",
};
const TRIS_RENDEMENT = { rendement: "rendement_brut_pct", prix_m2: "prix_m2_median", loyer: "loyer_m2" };

function garder(l: Ligne, cles: string[]): Ligne {
  return Object.fromEntries(cles.map((c) => [c, l[c]]));
}

// ---------------------------- endpoints ----------------------------

export function creerApiLocale(charger: ChargeurMart) {
  const prixCommunes = () => charger("mart_prix_m2_par_commune");
  const trimestriel = () => charger("mart_evolution_trimestrielle");
  const rendements = () => charger("mart_rendement_locatif");
  const impactDpe = () => charger("mart_impact_dpe");
  const scores = () => charger("mart_score_investissement");

  const dep = (p: Params) => (present(p.departement) ? String(p.departement) : "06");
  const memeType = (l: Ligne, p: Params) => !present(p.type_bien) || l.type_bien === p.type_bien;

  async function communes(p: Params) {
    const prixMin = nombre(p.prix_m2_min);
    const prixMax = nombre(p.prix_m2_max);
    const popMin = nombre(p.population_min);
    const recherche = present(p.recherche) ? String(p.recherche).toLowerCase() : null;
    const filtrees = (await prixCommunes()).filter(
      (l) =>
        l.code_departement === dep(p) &&
        memeType(l, p) &&
        auMoins(l.prix_m2_median, prixMin) &&
        auPlus(l.prix_m2_median, prixMax) &&
        auMoins(l.population, popMin) &&
        (!recherche || String(l.nom_commune ?? "").toLowerCase().includes(recherche)),
    );
    const tri = choisir(p.tri, TRIS_COMMUNES, "ventes");
    const ordre = p.ordre === "asc" ? "asc" : "desc";
    const limit = entier(p.limit, 200, 1, 500);
    const offset = entier(p.offset, 0, 0, Number.MAX_SAFE_INTEGER);
    return {
      total: filtrees.length,
      limit,
      offset,
      resultats: trier(filtrees, TRIS_COMMUNES[tri], ordre).slice(offset, offset + limit),
    };
  }

  async function detailCommune(code: string, chemin: string) {
    const prix = (await prixCommunes()).filter((l) => l.code_commune === code);
    if (!prix.length) throw new ErreurApiLocale(404, chemin, `Commune ${code} inconnue (aucune vente analysée)`);
    return {
      code_commune: code,
      nom_commune: prix[0].nom_commune,
      prix,
      rendement: (await rendements())
        .filter((l) => l.code_commune === code)
        .map((l) => garder(l, ["type_bien", "loyer_m2", "loyer_fiabilite", "rendement_brut_pct"])),
      scores: (await scores())
        .filter((l) => l.code_commune === code)
        .map((l) =>
          garder(l, [
            "type_bien", "score_investissement", "score_prix", "score_rendement",
            "score_dynamique_marche", "score_dynamique_demo", "score_services", "score_tension",
          ]),
        ),
    };
  }

  async function tendances(p: Params) {
    const code = present(p.code_commune) ? String(p.code_commune) : null;
    const tMin = present(p.trimestre_min) ? String(p.trimestre_min) : null;
    const tMax = present(p.trimestre_max) ? String(p.trimestre_max) : null;
    const lignes = (await trimestriel())
      .filter(
        (l) =>
          l.code_departement === dep(p) &&
          (code ? l.maille === "commune" && l.code_commune === code : l.maille === "departement") &&
          memeType(l, p) &&
          (!tMin || l.trimestre >= tMin) &&
          (!tMax || l.trimestre <= tMax),
      )
      .sort((a, b) =>
        a.trimestre === b.trimestre
          ? a.type_bien < b.type_bien ? -1 : a.type_bien > b.type_bien ? 1 : 0
          : a.trimestre < b.trimestre ? -1 : 1,
      )
      .map((l) =>
        garder(l, [
          "maille", "code_commune", "nom_commune", "type_bien", "trimestre",
          "nb_ventes", "prix_m2_median", "prix_median", "surface_mediane",
        ]),
      );
    return { maille: code ? "commune" : "departement", resultats: lignes };
  }

  async function kpis(p: Params) {
    const d = dep(p);
    const evo = (await trimestriel()).filter((l) => l.code_departement === d);
    const maillesDep = evo.filter((l) => l.maille === "departement");
    const trimestresDep = maillesDep.map((l) => l.trimestre as string).sort();

    // 4 derniers trimestres présents (toutes mailles), puis agrégat à la maille département
    const derniers = new Set([...new Set(evo.map((l) => l.trimestre as string))].sort().slice(-4));
    const types = [...new Set(maillesDep.filter((l) => derniers.has(l.trimestre)).map((l) => l.type_bien as string))].sort();
    const parTypeBien = types.map((type) => {
      const lignes = maillesDep.filter((l) => l.type_bien === type && derniers.has(l.trimestre));
      const nb = lignes.reduce((s, l) => s + l.nb_ventes, 0);
      // sum(prix * nb) ignore les lignes sans prix, comme l'agrégat SQL
      const avecPrix = lignes.filter((l) => l.prix_m2_median != null);
      const pondere = avecPrix.reduce((s, l) => s + l.prix_m2_median * l.nb_ventes, 0);
      // Aucun prix renseigné → NULL comme en SQL, pas 0 €/m²
      return { type_bien: type, nb_ventes_12m: nb, prix_m2_median_12m: nb && avecPrix.length ? arrondi(pondere / nb, 0) : null };
    });

    const prix = (await prixCommunes()).filter((l) => l.code_departement === d);
    const evolutions = [...new Set(prix.map((l) => l.type_bien as string))].sort().map((type) => {
      const lignes = prix.filter((l) => l.type_bien === type);
      return {
        type_bien: type,
        evolution_1an_pct_mediane: arrondi(mediane(lignes.map((l) => l.evolution_1an_pct)), 2),
        evolution_3ans_pct_mediane: arrondi(mediane(lignes.map((l) => l.evolution_3ans_pct)), 2),
      };
    });

    const rend = (await rendements()).filter((l) => l.code_departement === d);
    return {
      departement: d,
      nb_ventes_total: maillesDep.length ? maillesDep.reduce((s, l) => s + l.nb_ventes, 0) : null,
      periode: [trimestresDep[0] ?? null, trimestresDep[trimestresDep.length - 1] ?? null],
      nb_communes: new Set(prix.map((l) => l.code_commune)).size,
      par_type_bien: parTypeBien,
      evolutions,
      rendement_brut_median: arrondi(mediane(rend.map((l) => l.rendement_brut_pct)), 2),
    };
  }

  async function dpeImpact(p: Params) {
    const lignes = (await impactDpe())
      .filter((l) => l.code_departement === dep(p) && memeType(l, p))
      .sort((a, b) =>
        a.type_bien === b.type_bien
          ? a.etiquette_dpe < b.etiquette_dpe ? -1 : a.etiquette_dpe > b.etiquette_dpe ? 1 : 0
          : a.type_bien < b.type_bien ? -1 : 1,
      )
      .map((l) =>
        garder(l, ["type_bien", "etiquette_dpe", "nb_ventes", "prix_m2_median", "ecart_vs_marche_pct", "conso_ep_m2_mediane"]),
      );
    return { resultats: lignes };
  }

  async function rendement(p: Params) {
    const rendementMin = nombre(p.rendement_min);
    const prixMax = nombre(p.prix_m2_max);
    const filtrees = (await rendements()).filter(
      (l) =>
        l.code_departement === dep(p) &&
        memeType(l, p) &&
        auMoins(l.rendement_brut_pct, rendementMin) &&
        auPlus(l.prix_m2_median, prixMax),
    );
    const tri = choisir(p.tri, TRIS_RENDEMENT, "rendement");
    const ordre = p.ordre === "asc" ? "asc" : "desc";
    const limit = entier(p.limit, 100, 1, 500);
    const offset = entier(p.offset, 0, 0, Number.MAX_SAFE_INTEGER);
    return {
      total: filtrees.length,
      limit,
      offset,
      resultats: trier(filtrees, TRIS_RENDEMENT[tri], ordre).slice(offset, offset + limit),
    };
  }

  async function opportunites(p: Params) {
    const scoreMin = nombre(p.score_min);
    const prixMax = nombre(p.prix_m2_max);
    const filtrees = (await scores()).filter(
      (l) =>
        l.code_departement === dep(p) &&
        memeType(l, p) &&
        auMoins(l.score_investissement, scoreMin) &&
        auPlus(l.prix_m2_median, prixMax),
    );
    return { resultats: trier(filtrees, "score_investissement", "desc").slice(0, entier(p.limit, 50, 1, 200)) };
  }

  async function estimation(p: Params, chemin: string) {
    const code = present(p.code_commune) ? String(p.code_commune) : "";
    const type = p.type_bien === "maison" ? "maison" : "appartement";
    const surface = nombre(p.surface);
    const etiquette = present(p.etiquette_dpe) ? String(p.etiquette_dpe) : null;
    if (!/^\d{5}$|^2[AB]\d{3}$/.test(code) || surface === undefined || surface <= 8 || surface >= 1000) {
      throw new ErreurApiLocale(422, chemin, "paramètres invalides");
    }
    const base = (await prixCommunes()).find((l) => l.code_commune === code && l.type_bien === type);
    if (!base || base.prix_m2_median == null || base.prix_m2_p25 == null || base.prix_m2_p75 == null) {
      throw new ErreurApiLocale(404, chemin, "Pas assez de ventes récentes dans cette commune pour estimer");
    }
    let ajustement = 0;
    if (etiquette) {
      const dpe = (await impactDpe()).find(
        (l) => l.code_departement === base.code_departement && l.type_bien === type && l.etiquette_dpe === etiquette,
      );
      if (dpe) ajustement = dpe.ecart_vs_marche_pct ?? 0;
    }
    const facteur = 1 + ajustement / 100;
    return {
      code_commune: code,
      nom_commune: base.nom_commune,
      type_bien: type,
      surface,
      etiquette_dpe: etiquette,
      prix_m2_reference: base.prix_m2_median,
      ajustement_dpe_pct: ajustement,
      prix_estime: arrondiPython(surface * base.prix_m2_median * facteur),
      fourchette_basse: arrondiPython(surface * base.prix_m2_p25 * facteur),
      fourchette_haute: arrondiPython(surface * base.prix_m2_p75 * facteur),
      fiabilite: {
        nb_ventes_24m: base.nb_ventes_24m,
        methode: "médiane communale 24 mois × ajustement DPE départemental (quartiles locaux)",
      },
    };
  }

  async function meta() {
    const trimestres = (await trimestriel()).map((l) => l.trimestre as string).sort();
    return {
      departements: [...new Set((await prixCommunes()).map((l) => l.code_departement as string))].sort(),
      premier_trimestre: trimestres[0] ?? null,
      dernier_trimestre: trimestres[trimestres.length - 1] ?? null,
      marts: [
        "mart_prix_m2_par_commune", "mart_evolution_trimestrielle", "mart_rendement_locatif",
        "mart_impact_dpe", "mart_score_investissement",
      ],
    };
  }

  /** Aiguillage : même chemin et mêmes paramètres que l'API HTTP. */
  return async function get(chemin: string, params: Params = {}): Promise<unknown> {
    const route = chemin.replace(/\/+$/, "");
    switch (route) {
      case "/api/v1/communes": return communes(params);
      case "/api/v1/tendances": return tendances(params);
      case "/api/v1/kpis": return kpis(params);
      case "/api/v1/dpe/impact": return dpeImpact(params);
      case "/api/v1/rendement": return rendement(params);
      case "/api/v1/opportunites": return opportunites(params);
      case "/api/v1/estimation": return estimation(params, chemin);
      case "/api/v1/meta": return meta();
    }
    const detail = route.match(/^\/api\/v1\/communes\/([^/]+)$/);
    if (detail) return detailCommune(decodeURIComponent(detail[1]), chemin);
    throw new ErreurApiLocale(404, chemin, "route inconnue");
  };
}
