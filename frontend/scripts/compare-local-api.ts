/**
 * Vérifie que l'API locale (lib/local-api.ts + public/data/*.json) répond
 * comme la vraie API FastAPI, endpoint par endpoint, sur un jeu de requêtes
 * couvrant toutes les vues du site et les filtres de leurs curseurs.
 *
 * Prérequis : l'API tourne (docker compose up) sur les MÊMES marts gold que
 * l'export JSON. Usage, depuis frontend/ :
 *   node scripts/compare-local-api.ts [http://localhost:8001]
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { creerApiLocale, decompacter, type Params } from "../lib/local-api.ts";

const API = process.argv[2] ?? "http://localhost:8001";
const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "data");
const locale = creerApiLocale(async (mart) =>
  decompacter(JSON.parse(readFileSync(join(DATA, `${mart}.json`), "utf8"))),
);

const TOLERANCE = 1e-5; // l'export arrondit les flottants à 6 décimales

/** Liste les différences entre deux valeurs JSON (chemin : attendu ≠ obtenu). */
function differences(attendu: any, obtenu: any, chemin = ""): string[] {
  if (typeof attendu === "number" && typeof obtenu === "number") {
    return Math.abs(attendu - obtenu) <= TOLERANCE ? [] : [`${chemin} : ${attendu} ≠ ${obtenu}`];
  }
  if (attendu === null || obtenu === null || typeof attendu !== "object" || typeof obtenu !== "object") {
    return attendu === obtenu ? [] : [`${chemin} : ${JSON.stringify(attendu)} ≠ ${JSON.stringify(obtenu)}`];
  }
  if (Array.isArray(attendu) !== Array.isArray(obtenu)) return [`${chemin} : tableau vs objet`];
  if (Array.isArray(attendu) && attendu.length !== obtenu.length) {
    return [`${chemin} : ${attendu.length} éléments ≠ ${obtenu.length}`];
  }
  const cles = new Set([...Object.keys(attendu), ...Object.keys(obtenu)]);
  return [...cles].flatMap((c) => differences(attendu[c], obtenu[c], `${chemin}/${c}`));
}

const cleLigne = (l: any) =>
  JSON.stringify([l.commune_type_id ?? l.code_commune ?? "", l.type_bien ?? "", l.trimestre ?? "", l.etiquette_dpe ?? ""]);
const parCle = (lignes: any[]) => [...lignes].sort((a, b) => (cleLigne(a) < cleLigne(b) ? -1 : cleLigne(a) > cleLigne(b) ? 1 : 0));

/**
 * Un tri SQL ne fixe pas l'ordre des ex æquo. On vérifie donc séparément :
 *  - `ordreTri` : la colonne de tri sort dans le même ordre des deux côtés ;
 *  - `resultats` : mêmes lignes, comparées triées par clé stable. Si la liste
 *    est coupée par `limit`, les ex æquo de la dernière valeur peuvent
 *    légitimement différer (lequel entre dans le top 30 est arbitraire) : on
 *    les écarte de la comparaison ligne à ligne, leur nombre reste vérifié.
 * Les fiches commune renvoient des listes sans ORDER BY : triées par clé.
 */
function normaliser(reponse: any, colonneTri?: string, limiteDemandee?: number): any {
  if (!reponse || typeof reponse !== "object") return reponse;
  if (Array.isArray(reponse.prix)) {
    return { ...reponse, prix: parCle(reponse.prix), rendement: parCle(reponse.rendement), scores: parCle(reponse.scores) };
  }
  if (!Array.isArray(reponse.resultats)) return reponse;
  let lignes: any[] = reponse.resultats;
  const ordreTri = colonneTri ? lignes.map((l) => l[colonneTri]) : undefined;
  // Coupée par `limit` ? (limit renvoyé par la réponse, sinon celui de la requête)
  const limite = reponse.limit ?? limiteDemandee;
  if (colonneTri && limite !== undefined && lignes.length === limite) {
    const derniere = lignes[lignes.length - 1][colonneTri];
    lignes = lignes.filter((l) => l[colonneTri] !== derniere);
  }
  return { ...reponse, ordreTri, resultats: parCle(lignes) };
}

type Cas = { chemin: string; params?: Params; tri?: string };
const T = ["appartement", "maison", undefined] as const;
const cas: Cas[] = [{ chemin: "/api/v1/kpis", params: { departement: "06" } }, { chemin: "/api/v1/meta" }];

for (const type_bien of T) {
  cas.push({ chemin: "/api/v1/communes", params: { departement: "06", type_bien, limit: 500 }, tri: "nb_ventes_total" });
  cas.push({ chemin: "/api/v1/dpe/impact", params: { departement: "06", type_bien } });
  cas.push({ chemin: "/api/v1/tendances", params: { departement: "06", type_bien } });
  cas.push({ chemin: "/api/v1/opportunites", params: { departement: "06", type_bien, limit: 200 }, tri: "score_investissement" });
  cas.push({ chemin: "/api/v1/rendement", params: { departement: "06", type_bien, limit: 500 }, tri: "rendement_brut_pct" });
  for (const score_min of [0, 40, 55, 70, 95]) {
    for (const prix_m2_max of [undefined, 3000, 5000, 8000]) {
      cas.push({ chemin: "/api/v1/opportunites", params: { departement: "06", type_bien, score_min, prix_m2_max, limit: 30 }, tri: "score_investissement" });
    }
  }
  for (const rendement_min of [undefined, 2, 4.5, 6, 12]) {
    for (const prix_m2_max of [undefined, 2500, 4000, 9500]) {
      cas.push({ chemin: "/api/v1/rendement", params: { departement: "06", type_bien, rendement_min, prix_m2_max, limit: 500 }, tri: "rendement_brut_pct" });
    }
  }
}
// Filtre « loyers fiables seulement » (vue Opportunités par défaut)
for (const type_bien of T) {
  for (const score_min of [0, 50, 65]) {
    cas.push({ chemin: "/api/v1/opportunites", params: { departement: "06", type_bien, score_min, loyer_fiable: true, limit: 30 }, tri: "score_investissement" });
  }
  cas.push({ chemin: "/api/v1/opportunites", params: { type_bien, loyer_fiable: false, limit: 200 }, tri: "score_investissement" });
  cas.push({ chemin: "/api/v1/rendement", params: { type_bien, loyer_fiable: true, limit: 500 }, tri: "rendement_brut_pct" });
}
// Tris, ordres, pagination, recherche, bornes de prix et de population
for (const [tri, colonne] of [["prix_m2", "prix_m2_median"], ["ventes", "nb_ventes_total"], ["evolution", "evolution_1an_pct"], ["population", "population"], ["nom", "nom_commune"]]) {
  for (const ordre of ["asc", "desc"]) {
    cas.push({ chemin: "/api/v1/communes", params: { tri, ordre, limit: 500 }, tri: colonne });
  }
}
cas.push({ chemin: "/api/v1/communes", params: { tri: "nom", ordre: "asc", limit: 20, offset: 40 }, tri: "nom_commune" });
cas.push({ chemin: "/api/v1/communes", params: { recherche: "saint", limit: 500 }, tri: "nb_ventes_total" });
cas.push({ chemin: "/api/v1/communes", params: { recherche: "CANN", type_bien: "maison" }, tri: "nb_ventes_total" });
cas.push({ chemin: "/api/v1/communes", params: { prix_m2_min: 4000, prix_m2_max: 6000, population_min: 10000, limit: 500 }, tri: "nb_ventes_total" });
cas.push({ chemin: "/api/v1/communes", params: { departement: "83" } });
for (const [tri, colonne] of [["rendement", "rendement_brut_pct"], ["prix_m2", "prix_m2_median"], ["loyer", "loyer_m2"]]) {
  for (const ordre of ["asc", "desc"]) {
    cas.push({ chemin: "/api/v1/rendement", params: { tri, ordre, limit: 500 }, tri: colonne });
  }
}
cas.push({ chemin: "/api/v1/tendances", params: { trimestre_min: "2023Q1", trimestre_max: "2024Q2", type_bien: "maison" } });
cas.push({ chemin: "/api/v1/tendances", params: { code_commune: "06088", type_bien: "maison" } });
cas.push({ chemin: "/api/v1/tendances", params: { code_commune: "06029" } });
cas.push({ chemin: "/api/v1/kpis", params: { departement: "83" } });
cas.push({ chemin: "/api/v1/communes", params: { limit: 50, offset: 10000 } });
cas.push({ chemin: "/api/v1/rendement", params: { limit: 10, offset: 295, tri: "prix_m2", ordre: "asc" }, tri: "prix_m2_median" });

// Toutes les communes : fiche détail, tendances communales, estimations
const communes = ((await locale("/api/v1/communes", { limit: 500, type_bien: "appartement" })) as any).resultats;
const maisons = ((await locale("/api/v1/communes", { limit: 500, type_bien: "maison" })) as any).resultats;
const codes = [...new Set([...communes, ...maisons].map((c: any) => c.code_commune as string))];
for (const code of codes) {
  cas.push({ chemin: `/api/v1/communes/${code}` });
  cas.push({ chemin: "/api/v1/tendances", params: { departement: "06", code_commune: code, type_bien: "appartement" } });
  for (const type_bien of ["appartement", "maison"]) {
    for (const [surface, etiquette_dpe] of [[45, undefined], [72.5, "A"], [130, "F"], [9, "G"]] as const) {
      cas.push({ chemin: "/api/v1/estimation", params: { code_commune: code, type_bien, surface, etiquette_dpe } });
    }
  }
}
// Erreurs attendues : commune inconnue (404), surface hors bornes (422)
cas.push({ chemin: "/api/v1/communes/99999" });
cas.push({ chemin: "/api/v1/estimation", params: { code_commune: "99999", surface: 50 } });
cas.push({ chemin: "/api/v1/estimation", params: { code_commune: "06029", surface: 5 } });
cas.push({ chemin: "/api/v1/estimation", params: { code_commune: "06029", surface: 1000 } });

let echecs = 0;
const parRoute = new Map<string, number>();
for (const { chemin, params = {}, tri } of cas) {
  const url = new URL(chemin, API);
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  const res = await fetch(url);
  const attendu = res.ok ? await res.json() : { erreur: res.status };
  let obtenu: any;
  try {
    obtenu = await locale(chemin, params);
  } catch (e: any) {
    obtenu = { erreur: e.statut ?? String(e) };
  }
  const limite = typeof params.limit === "number" ? params.limit : undefined;
  const diffs = differences(normaliser(attendu, tri, limite), normaliser(obtenu, tri, limite));
  const route = chemin.replace(/\/\d{5}$/, "/{code}");
  parRoute.set(route, (parRoute.get(route) ?? 0) + 1);
  if (diffs.length) {
    echecs++;
    if (echecs <= 15) console.log(`✗ ${chemin} ${JSON.stringify(params)}\n   ${diffs.slice(0, 4).join("\n   ")}`);
  }
}
console.log([...parRoute].map(([r, n]) => `${r} : ${n} requêtes`).join("\n"));
console.log(echecs ? `\n✗ ${echecs} requête(s) différente(s) sur ${cas.length}` : `\n✔ ${cas.length} requêtes identiques entre l'API et la version locale`);
process.exit(echecs ? 1 : 0);
