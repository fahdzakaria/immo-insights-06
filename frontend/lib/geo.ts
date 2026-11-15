/** Géométrie légère pour dessiner de vrais contours sans bibliothèque :
 *  projection équirectangulaire corrigée de la latitude (suffisant à
 *  l'échelle d'un département). */

export type Geometrie = GeoJSON.Polygon | GeoJSON.MultiPolygon;
export type Boite = [[number, number], [number, number]];

export const anneaux = (g: Geometrie): GeoJSON.Position[][][] =>
  g.type === "Polygon" ? [g.coordinates] : g.coordinates;

export function boite(g: Geometrie): Boite {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  for (const poly of anneaux(g))
    for (const anneau of poly)
      for (const [x, y] of anneau) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
  return [[x0, y0], [x1, y1]];
}

/** Projette une boîte géographique dans un cadre w×h (marge `pad`, centré). */
export function projection(b: Boite, w: number, h: number, pad = 0) {
  const k = Math.cos((((b[0][1] + b[1][1]) / 2) * Math.PI) / 180);
  const dx = (b[1][0] - b[0][0]) * k;
  const dy = b[1][1] - b[0][1];
  const s = Math.min((w - 2 * pad) / dx, (h - 2 * pad) / dy);
  const ox = (w - dx * s) / 2;
  const oy = (h - dy * s) / 2;
  return ([x, y]: GeoJSON.Position): [number, number] => [ox + (x - b[0][0]) * k * s, oy + (b[1][1] - y) * s];
}

/** Chemin SVG d'une géométrie. */
export function cheminSvg(g: Geometrie, proj: (p: GeoJSON.Position) => [number, number]): string {
  let d = "";
  for (const poly of anneaux(g))
    for (const anneau of poly) {
      anneau.forEach((p, i) => {
        const [x, y] = proj(p);
        d += `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      });
      d += "Z";
    }
  return d;
}

/** Trace une géométrie dans un contexte canvas (à remplir ou tracer ensuite). */
export function tracer(ctx: CanvasRenderingContext2D, g: Geometrie, proj: (p: GeoJSON.Position) => [number, number]) {
  ctx.beginPath();
  for (const poly of anneaux(g))
    for (const anneau of poly) {
      anneau.forEach((p, i) => {
        const [x, y] = proj(p);
        if (i) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      });
      ctx.closePath();
    }
}
