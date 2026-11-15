"use client";

/**
 * Aperçu de la vraie carte pour le hero : les communes du littoral en SVG,
 * colorées avec la même rampe que la page Carte. Léger (pas de MapLibre),
 * survol = nom et prix, clic = ouvre la carte. Moins de 5 ventes : éteint, comme sur la carte.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CommunePrix } from "@/lib/api";
import { SEUIL_VENTES_AFFICHAGE } from "@/lib/api";
import { euro, nombre } from "@/lib/format";
import { cheminSvg, type Boite, type Geometrie, projection } from "@/lib/geo";
import { couleurPrix, ETEINT } from "@/lib/palette";

const LITTORAL: Boite = [[6.86, 43.5], [7.54, 43.84]];
const W = 640;
const H = 420;

export default function ApercuCarte({
  geo,
  communes,
  seuils,
}: {
  geo: GeoJSON.FeatureCollection;
  communes: CommunePrix[];
  seuils: number[];
}) {
  const [survol, setSurvol] = useState<string | null>(null);
  const parCode = useMemo(() => new Map(communes.map((c) => [c.code_commune, c])), [communes]);
  const formes = useMemo(() => {
    const proj = projection(LITTORAL, W, H);
    return geo.features.map((f) => {
      const code = String((f.properties as { code: string }).code);
      const c = parCode.get(code);
      const valeur = c && (c.nb_ventes_24m ?? 0) >= SEUIL_VENTES_AFFICHAGE ? c.prix_m2_median : null;
      return { code, nom: String((f.properties as { nom: string }).nom), d: cheminSvg(f.geometry as Geometrie, proj), valeur, ventes: c?.nb_ventes_24m ?? 0 };
    });
  }, [geo, parCode]);
  const actif = formes.find((f) => f.code === survol);

  return (
    <Link
      href="/carte"
      aria-label="Ouvrir la carte des prix"
      className="glass group block overflow-hidden !rounded-[20px] p-1.5 transition-colors hover:!border-line2"
    >
      <div className="relative overflow-hidden rounded-[14px] bg-[#0b0d10]">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" onPointerLeave={() => setSurvol(null)}>
          {formes.map((f) => (
            <path
              key={f.code}
              d={f.d}
              fill={f.valeur == null ? ETEINT : couleurPrix(f.valeur, seuils)}
              stroke={f.code === survol ? "#f2efe9" : "#000"}
              strokeWidth={f.code === survol ? 1.6 : 0.6}
              onPointerEnter={() => setSurvol(f.code)}
              style={{ transition: "stroke .15s" }}
            />
          ))}
          {/* le survolé repasse au-dessus pour que son contour soit entier */}
          {actif && <path d={actif.d} fill="none" stroke="#f2efe9" strokeWidth={1.6} pointerEvents="none" />}
        </svg>
        <div className="pointer-events-none absolute right-3 top-3 rounded-[10px] border border-line2 bg-black/80 px-3 py-2 text-right">
          {actif ? (
            <>
              <div className="text-sm text-ink">{actif.nom}</div>
              <div className="label-mono tabular !text-accent">
                {actif.valeur == null ? "Pas assez de ventes" : `${euro(actif.valeur)}/m²`}
              </div>
              <div className="legende">{nombre(actif.ventes)} vente{actif.ventes > 1 ? "s" : ""} sur 24 mois</div>
            </>
          ) : (
            <div className="legende">Survolez une commune</div>
          )}
        </div>
        <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-2 rounded-full border border-line2 bg-black/80 px-3 py-1.5">
          <span className="label-mono !text-ink">€/m² médian · 24 mois</span>
        </div>
      </div>
      <div className="flex items-end justify-between px-3 pb-2 pt-3">
        <p className="legende">
          <b>Littoral, communes</b>
          appartements · mêmes couleurs que la carte
        </p>
        <span className="hidden shrink-0 text-sm text-muted transition-colors group-hover:text-ink sm:inline">Ouvrir la carte →</span>
      </div>
    </Link>
  );
}
