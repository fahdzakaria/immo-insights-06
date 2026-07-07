"use client";

/** Bandeau de cotation façon terminal : les communes défilent en continu
 *  avec prix médian et variation 1 an (▲ vert / ▼ corail). Pause au survol. */

import type { CommunePrix } from "@/lib/api";
import { euro } from "@/lib/format";

export default function Ticker({ communes }: { communes: CommunePrix[] }) {
  const lignes = communes
    .filter((c) => c.prix_m2_median && c.nb_ventes_24m && c.nb_ventes_24m >= 20)
    .sort((a, b) => (b.nb_ventes_24m ?? 0) - (a.nb_ventes_24m ?? 0))
    .slice(0, 36);
  if (!lignes.length) return null;

  const Item = ({ c }: { c: CommunePrix }) => {
    const evo = c.evolution_1an_pct;
    return (
      <span className="label-mono flex shrink-0 items-baseline gap-2 border-r border-line px-5 py-2.5">
        <span className="!text-ink font-medium">{c.nom_commune}</span>
        <span className="tabular !text-accent">{euro(c.prix_m2_median)}/m²</span>
        {evo != null && (
          <span className={`tabular ${evo >= 0 ? "!text-good" : "!text-bad"}`}>
            {evo >= 0 ? "▲" : "▼"} {Math.abs(evo).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %
          </span>
        )}
      </span>
    );
  };

  return (
    <div className="ticker -mx-4 sm:-mx-6" aria-hidden>
      <div className="ticker-track">
        {/* piste doublée pour un défilement sans couture */}
        {[0, 1].map((serie) => (
          <div key={serie} className="flex">
            {lignes.map((c) => (
              <Item key={`${serie}-${c.commune_type_id}`} c={c} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
