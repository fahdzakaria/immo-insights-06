/**
 * Client de données typé — tout vient des marts gold. Deux sources possibles,
 * choisies au build par NEXT_PUBLIC_DATA_SOURCE :
 *  - "static" (défaut) : marts embarqués en JSON (public/data), filtrés dans
 *    le navigateur par lib/local-api.ts — aucun serveur à joindre ;
 *  - "api" : l'API FastAPI (NEXT_PUBLIC_API_URL), utilisée par le stack Docker.
 */

import { creerApiLocale, decompacter, type Ligne } from "./local-api";

export const SOURCE_DONNEES: "static" | "api" =
  process.env.NEXT_PUBLIC_DATA_SOURCE === "api" ? "api" : "static";

/** En dessous de ce nombre de ventes sur 24 mois, une médiane communale ne
 *  veut rien dire : carte, maquette 3D et courbes de tendance ne l'affichent pas,
 *  le comparateur le signale.
 *  Même valeur que le seuil du rendement (mart dbt) et de l'estimateur
 *  (SEUIL_VENTES_ESTIMATION dans local-api.ts et investissement.py) : à garder alignés. */
export const SEUIL_VENTES_AFFICHAGE = 5;

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

/** Chaque mart JSON n'est téléchargé qu'une fois par session (promesse mise en cache). */
const martsEnCache = new Map<string, Promise<Ligne[]>>();

function chargerMart(mart: string): Promise<Ligne[]> {
  let promesse = martsEnCache.get(mart);
  if (!promesse) {
    promesse = fetch(`/data/${mart}.json`).then((res) => {
      if (!res.ok) throw new Error(`Données indisponibles (${res.status} sur ${mart}.json)`);
      return res.json().then(decompacter);
    });
    // Un échec réseau ne doit pas rester en cache : le prochain appel réessaie
    promesse.catch(() => martsEnCache.delete(mart));
    martsEnCache.set(mart, promesse);
  }
  return promesse;
}

const apiLocale = creerApiLocale(chargerMart);

export type TypeBien = "appartement" | "maison";

export interface CommunePrix {
  commune_type_id: string;
  code_commune: string;
  nom_commune: string;
  code_departement: string;
  type_bien: TypeBien;
  nb_ventes_total: number;
  nb_ventes_24m: number | null;
  prix_m2_median: number | null;
  prix_m2_p25: number | null;
  prix_m2_p75: number | null;
  prix_median: number | null;
  surface_mediane: number | null;
  evolution_1an_pct: number | null;
  evolution_3ans_pct: number | null;
  latitude: number | null;
  longitude: number | null;
  population: number | null;
  niveau_vie_median: number | null;
  taux_pauvrete: number | null;
}

export interface Kpis {
  departement: string;
  nb_ventes_total: number;
  periode: [string, string];
  nb_communes: number;
  par_type_bien: { type_bien: TypeBien; nb_ventes_12m: number; prix_m2_median_12m: number }[];
  evolutions: { type_bien: TypeBien; evolution_1an_pct_mediane: number; evolution_3ans_pct_mediane: number }[];
  rendement_brut_median: number;
}

export interface PointTendance {
  maille: string;
  code_commune: string | null;
  nom_commune: string | null;
  type_bien: TypeBien;
  trimestre: string;
  nb_ventes: number;
  prix_m2_median: number;
  prix_median: number;
  surface_mediane: number;
}

export interface Rendement {
  code_commune: string;
  nom_commune: string;
  type_bien: TypeBien;
  nb_ventes_24m: number;
  prix_m2_median: number;
  loyer_m2: number | null;
  /** Bornes de l'intervalle de prédiction du loyer (carte des loyers). */
  loyer_m2_bas: number | null;
  loyer_m2_haut: number | null;
  loyer_fiabilite: string | null;
  loyer_nb_annonces: number | null;
  rendement_brut_pct: number | null;
  rendement_bas_pct: number | null;
  rendement_haut_pct: number | null;
  /** Loyer prédit à l'échelle de la commune ET ≥ 20 ventes sur 24 mois. */
  rendement_fiable: boolean;
}

export interface ImpactDpe {
  type_bien: TypeBien;
  etiquette_dpe: string;
  nb_ventes: number;
  prix_m2_median: number;
  ecart_vs_marche_pct: number;
  /** Demi-largeur de l'intervalle de confiance à 95 % de l'écart. */
  ecart_ic95_pct: number;
  /** Assez de ventes et écart distinct de zéro : appliqué par l'estimateur. */
  fiable: boolean;
  conso_ep_m2_mediane: number;
}

export interface Opportunite {
  code_commune: string;
  nom_commune: string;
  type_bien: TypeBien;
  nb_ventes_24m: number;
  prix_m2_median: number;
  rendement_brut_pct: number | null;
  loyer_fiabilite: string | null;
  rendement_fiable: boolean;
  evolution_3ans_pct: number | null;
  evolution_population_pct: number | null;
  pois_moyens_500m: number | null;
  score_prix: number;
  score_rendement: number;
  score_dynamique_marche: number;
  score_dynamique_demo: number;
  score_services: number;
  score_tension: number;
  score_investissement: number;
}

export interface Estimation {
  code_commune: string;
  nom_commune: string;
  type_bien: TypeBien;
  surface: number;
  etiquette_dpe: string | null;
  prix_m2_reference: number;
  ajustement_dpe_pct: number;
  ajustement_dpe_applique: boolean;
  ajustement_dpe_motif: string | null;
  prix_estime: number;
  fourchette_basse: number;
  fourchette_haute: number;
  fiabilite: { nb_ventes_24m: number; niveau: "faible" | "correcte" | "bonne"; methode: string };
}

export interface DetailCommune {
  code_commune: string;
  nom_commune: string;
  prix: CommunePrix[];
  rendement: Pick<Rendement, "type_bien" | "loyer_m2" | "loyer_fiabilite" | "rendement_brut_pct" | "rendement_fiable">[];
  scores: (Pick<
    Opportunite,
    | "type_bien" | "score_investissement" | "score_prix" | "score_rendement"
    | "score_dynamique_marche" | "score_dynamique_demo" | "score_services" | "score_tension"
  >)[];
}

/** GET d'un endpoint (valeurs null/undefined omises) — local ou HTTP selon SOURCE_DONNEES. */
export async function apiGet<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined | null> = {},
): Promise<T> {
  if (SOURCE_DONNEES === "static") return apiLocale(path, params) as Promise<T>;
  const url = new URL(path, API_URL);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} sur ${path}`);
  return res.json();
}
