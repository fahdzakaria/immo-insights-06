/** Formatteurs FR partagés. */

export const euro = (n: number | null | undefined, decimales = 0): string =>
  n == null
    ? "—"
    : new Intl.NumberFormat("fr-FR", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: decimales,
      }).format(n);

export const nombre = (n: number | null | undefined): string =>
  n == null ? "—" : new Intl.NumberFormat("fr-FR").format(n);

export const pct = (n: number | null | undefined, signe = true): string => {
  if (n == null) return "—";
  const s = signe && n > 0 ? "+" : "";
  return `${s}${n.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
};

/** Couleur d'une évolution : vert si hausse, rouge si baisse. */
export const evolClass = (n: number | null | undefined): string =>
  n == null ? "text-muted" : n >= 0 ? "text-good" : "text-bad";

export const DPE_COULEURS: Record<string, string> = {
  A: "#22c55e", B: "#84cc16", C: "#eab308", D: "#f59e0b",
  E: "#f97316", F: "#ef4444", G: "#b91c1c",
};
