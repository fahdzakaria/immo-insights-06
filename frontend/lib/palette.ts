/** Rampe « braise » partagée par la carte, l'aperçu et les visuels :
 *  une teinte veut dire le même prix partout sur le site. */

export const PALETTE_PRIX = ["#2a1a0c", "#43260e", "#653410", "#8f4a12", "#bd6614", "#e88a1a", "#ffb547"];

/** Zone sans chiffre (moins de 5 ventes) : éteinte, jamais colorée. */
export const ETEINT = "#141414";

/** n seuils de quantiles (bornes entre classes). */
export function quantiles(vals: number[], n: number): number[] {
  const tri = [...vals].sort((a, b) => a - b);
  if (!tri.length) return [];
  return Array.from({ length: n }, (_, i) => tri[Math.floor(((i + 1) / (n + 1)) * (tri.length - 1))]);
}

/** Seuils de classes pour la rampe prix, sans doublon. */
export function seuilsPrix(vals: number[]): number[] {
  return [...new Set(quantiles(vals, PALETTE_PRIX.length - 1))];
}

/** Couleur d'un prix selon des seuils de quantiles (null → éteint). */
export function couleurPrix(v: number | null | undefined, seuils: number[]): string {
  if (v == null) return ETEINT;
  let i = 0;
  while (i < seuils.length && v >= seuils[i]) i++;
  return PALETTE_PRIX[Math.min(i, PALETTE_PRIX.length - 1)];
}
