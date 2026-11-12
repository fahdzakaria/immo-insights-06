"use client";

/** Vue Rendement : nuage prix vs rendement + classement filtrable. */

import { useState } from "react";
import {
  CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { Curseur, ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, Reveal, TitreSection } from "@/components/ui";
import type { Rendement, TypeBien } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, nombre } from "@/lib/format";

export default function PageRendement() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [rendementMin, setRendementMin] = useState(0);
  const [prixMax, setPrixMax] = useState(10000);
  // Par défaut : seulement les loyers mesurés localement (les autres donnent des rendements irréalistes)
  const [loyerFiable, setLoyerFiable] = useState(true);

  const { data, erreur } = useApi<{ total: number; resultats: Rendement[] }>("/api/v1/rendement", {
    departement: "06",
    type_bien: typeBien,
    rendement_min: rendementMin || undefined,
    prix_m2_max: prixMax < 10000 ? prixMax : undefined,
    loyer_fiable: loyerFiable || undefined,
    limit: 500,
  });

  const lignes = (data?.resultats ?? []).filter((r) => r.rendement_brut_pct != null);

  return (
    <div className="pt-8">
      <TitreSection
        sur="Rendement locatif"
        titre="Où le loyer rembourse le mieux l'achat"
        sousTitre="Rendement brut = loyer de référence × 12 ÷ prix d'achat au m². Loyers : carte officielle 2025, loyers d'annonce charges comprises — le rendement réel hors charges est plus bas."
      />
      <div className="glass mb-6 flex flex-wrap items-end gap-6 px-5 py-4">
        <ToggleTypeBien valeur={typeBien} onChange={(t) => t && setTypeBien(t)} />
        <div className="w-52">
          <Curseur label="Rendement minimum" valeur={rendementMin} onChange={setRendementMin}
                   min={0} max={10} pas={0.5} format={(v) => `${v} %`} />
        </div>
        <div className="w-52">
          <Curseur label="Prix max €/m²" valeur={prixMax} onChange={setPrixMax}
                   min={1000} max={10000} pas={250}
                   format={(v) => (v >= 10000 ? "sans limite" : euro(v))} />
        </div>
        <button
          onClick={() => setLoyerFiable((v) => !v)}
          aria-pressed={loyerFiable}
          title="Loyer prédit à l'échelle de la commune (assez d'annonces locales) et au moins 20 ventes. Décoché : inclut les communes au loyer extrapolé d'une zone plus large."
          className={`label-mono cursor-pointer border border-ink px-4 py-2 transition-colors ${
            loyerFiable ? "bg-ink !text-bg" : "hover:bg-ink/5"}`}
        >
          {loyerFiable ? "✓ " : ""}Loyers fiables seulement
        </button>
        <span className="ml-auto text-sm text-muted">{lignes.length} communes</span>
      </div>

      {erreur && <Erreur message={erreur} />}
      {!erreur && !data && <Chargement />}

      {lignes.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Reveal className="lg:col-span-3">
            <div className="glass h-full px-4 py-6">
              <h3 className="label-mono mb-2 px-2">
                Prix d'achat vs rendement — chaque point est une commune
              </h3>
              <ResponsiveContainer width="100%" height={380}>
                <ScatterChart margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid stroke="rgba(232,228,214,0.08)" />
                  <XAxis type="number" dataKey="prix_m2_median" name="Prix €/m²" stroke="#8a8574"
                         tickLine={false} axisLine={{ stroke: "#e8e4d6" }}
                         tick={{ fontFamily: "var(--font-plexmono)", fontSize: 12 }}
                         tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                         domain={["dataMin - 200", "dataMax + 200"]} />
                  <YAxis type="number" dataKey="rendement_brut_pct" name="Rendement" unit=" %"
                         stroke="#8a8574" tickLine={false} width={54}
                         tick={{ fontFamily: "var(--font-plexmono)", fontSize: 12 }} />
                  <ZAxis type="number" dataKey="nb_ventes_24m" range={[30, 420]} name="Ventes" />
                  <Tooltip
                    cursor={{ strokeDasharray: "4 4", stroke: "rgba(232,228,214,.35)" }}
                    contentStyle={{ background: "#14140f", border: "1px solid #ffb020", borderRadius: 2,
                                    fontFamily: "var(--font-plexmono)", fontSize: 12, color: "#e8e4d6" }}
                    formatter={(v: number, nom: string) =>
                      nom === "Prix €/m²" ? euro(v) : nom === "Rendement" ? `${v} %` : nombre(v)}
                    labelFormatter={() => ""}
                  />
                  <Scatter data={lignes} fill="#ffb020" fillOpacity={0.55} stroke="#ffb020" animationDuration={600} />
                </ScatterChart>
              </ResponsiveContainer>
              <p className="label-mono px-2">Taille du point = volume de ventes (fiabilité).</p>
            </div>
          </Reveal>

          <Reveal delay={0.08} className="lg:col-span-2">
            <div className="glass max-h-[500px] overflow-auto px-2 py-3">
              <table className="w-full text-sm">
                <thead className="label-mono sticky top-0 border-b border-ink bg-panel text-left">
                  <tr>
                    <th className="px-3 py-2">Commune</th>
                    <th className="px-3 py-2 text-right">€/m²</th>
                    <th className="px-3 py-2 text-right">Loyer</th>
                    <th className="px-3 py-2 text-right">Rdt</th>
                  </tr>
                </thead>
                <tbody>
                  {lignes.slice(0, 40).map((r) => (
                    <tr key={r.code_commune} className="border-t border-line transition-colors hover:bg-accent/5">
                      <td className="px-3 py-2">
                        {r.nom_commune}
                        {!r.rendement_fiable && (
                          <span title="Loyer extrapolé d'une zone plus large que la commune, ou moins de 20 ventes" className="ml-1 text-warn">*</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-muted">{euro(r.prix_m2_median)}</td>
                      <td className="px-3 py-2 text-right text-muted">{r.loyer_m2 ? `${r.loyer_m2} €` : "—"}</td>
                      <td className="px-3 py-2 text-right font-bold text-good"
                          title={r.rendement_bas_pct != null && r.rendement_haut_pct != null
                            ? `Fourchette selon l'intervalle de prédiction du loyer : ${r.rendement_bas_pct} % à ${r.rendement_haut_pct} %`
                            : undefined}>
                        {r.rendement_brut_pct} %
                        {r.rendement_bas_pct != null && r.rendement_haut_pct != null && (
                          <div className="text-[11px] font-normal text-muted">
                            {r.rendement_bas_pct}–{r.rendement_haut_pct}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="px-3 py-2 text-xs text-muted">
                * loyer extrapolé d'une zone plus large que la commune (trop peu d'annonces locales) ou moins de 20 ventes : rendement peu fiable.
                Sous chaque rendement : fourchette selon l'intervalle de prédiction du loyer.
              </p>
            </div>
          </Reveal>
        </div>
      )}
    </div>
  );
}
