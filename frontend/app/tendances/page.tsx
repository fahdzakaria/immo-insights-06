"use client";

/** Vue Tendances : séries trimestrielles prix + volumes, maille département ou commune. */

import { useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChampRecherche, ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, Reveal, TitreSection } from "@/components/ui";
import type { CommunePrix, PointTendance, TypeBien } from "@/lib/api";
import { SEUIL_VENTES_AFFICHAGE } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, nombre } from "@/lib/format";

const TOOLTIP_STYLE = {
  background: "#0a0a0a",
  border: "1px solid #2e2e2e",
  borderRadius: 12,
  fontFamily: "var(--font-geistmono)",
  fontSize: 12,
  color: "#f2efe9",
} as const;

const TICK_STYLE = { fontFamily: "var(--font-geistmono)", fontSize: 12 } as const;

export default function PageTendances() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [recherche, setRecherche] = useState("");

  const { data: communes } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: "appartement", limit: 500,
  });
  const communeChoisie = useMemo(
    () => communes?.resultats.find((c) => c.nom_commune.toLowerCase() === recherche.toLowerCase()),
    [communes, recherche],
  );

  const { data, erreur } = useApi<{ maille: string; resultats: PointTendance[] }>("/api/v1/tendances", {
    departement: "06",
    type_bien: typeBien,
    code_commune: communeChoisie?.code_commune,
  });

  // Un prix médian trimestriel sur moins de 5 ventes n'est pas un prix de marché :
  // le point est retiré de la courbe (le volume, lui, reste affiché).
  const serie = (data?.resultats ?? []).map((p) =>
    p.nb_ventes < SEUIL_VENTES_AFFICHAGE ? { ...p, prix_m2_median: null } : p,
  );
  const nbTrimestresMasques = serie.filter((p) => p.prix_m2_median == null).length;
  const perimetre = communeChoisie ? communeChoisie.nom_commune : "Alpes-Maritimes";

  return (
    <div className="pt-16 sm:pt-24">
      <TitreSection
        sur="Tendances"
        titre={`Prix et volumes trimestriels — ${perimetre}`}
        sousTitre="20 trimestres d'historique DVF. Tape un nom de commune pour zoomer sur son marché."
      />
      <div className="mb-10 flex flex-wrap items-center gap-3">
        <ToggleTypeBien valeur={typeBien} onChange={(t) => t && setTypeBien(t)} />
        <ChampRecherche
          valeur={recherche}
          onChange={setRecherche}
          liste={communes?.resultats.map((c) => c.nom_commune) ?? []}
          listeId="communes-tendances"
        />
        {recherche && !communeChoisie && (
          <span className="text-sm text-muted">↳ choisis une commune dans la liste</span>
        )}
      </div>

      {erreur && <Erreur message={erreur} />}
      {!erreur && serie.length === 0 && <Chargement />}

      {serie.length > 0 && (
        <div className="grid gap-8">
          <Reveal>
            <div className="glass px-4 py-6 sm:px-6">
              <h3 className="label-mono mb-4">Prix médian au m²</h3>
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={serie} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradPrix" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ffa31a" stopOpacity={0.16} />
                      <stop offset="100%" stopColor="#ffa31a" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="trimestre" stroke="#8f8c84" tickLine={false}
                         axisLine={{ stroke: "#2e2e2e" }} interval={3} tick={TICK_STYLE} />
                  <YAxis stroke="#8f8c84" tickLine={false} axisLine={false} tick={TICK_STYLE}
                         domain={["dataMin - 300", "dataMax + 300"]}
                         tickFormatter={(v: number) => `${Math.round(v / 100) / 10}k`} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(v) => [typeof v === "number" ? euro(v) + "/m²" : "trop peu de ventes", "Prix médian"]}
                  />
                  <Area type="monotone" dataKey="prix_m2_median" stroke="#ffa31a" strokeWidth={2.5}
                        fill="url(#gradPrix)" animationDuration={700} connectNulls={false} />
                </AreaChart>
              </ResponsiveContainer>
              {nbTrimestresMasques > 0 && (
                <p className="label-mono mt-3">
                  {nbTrimestresMasques === serie.length
                    ? `Moins de ${SEUIL_VENTES_AFFICHAGE} ventes par trimestre dans cette commune : pas de prix trimestriel fiable.`
                    : `${nbTrimestresMasques} trimestre${nbTrimestresMasques > 1 ? "s" : ""} sans point : moins de ${SEUIL_VENTES_AFFICHAGE} ventes, pas de prix fiable.`}
                </p>
              )}
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <div className="glass px-4 py-6 sm:px-6">
              <h3 className="label-mono mb-4">Volume de ventes</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={serie} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="trimestre" stroke="#8f8c84" tickLine={false}
                         axisLine={{ stroke: "#2e2e2e" }} interval={3} tick={TICK_STYLE} />
                  <YAxis stroke="#8f8c84" tickLine={false} axisLine={false} tick={TICK_STYLE} />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.05)" }}
                    contentStyle={TOOLTIP_STYLE}
                    // Sans ça, la ligne prend la couleur des barres (gris sombre) et se lit mal
                    itemStyle={{ color: "#ffa31a" }}
                    formatter={(v: number) => [nombre(v), "Ventes"]}
                  />
                  <Bar dataKey="nb_ventes" fill="#4a4740" radius={[3, 3, 0, 0]} animationDuration={700} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Reveal>
        </div>
      )}
    </div>
  );
}
