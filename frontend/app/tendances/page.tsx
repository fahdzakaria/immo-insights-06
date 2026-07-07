"use client";

/** Vue Tendances : séries trimestrielles prix + volumes, maille département ou commune. */

import { useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChampRecherche, ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, Reveal, TitreSection } from "@/components/ui";
import type { CommunePrix, PointTendance, TypeBien } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, nombre } from "@/lib/format";

const TOOLTIP_STYLE = {
  background: "#14140f",
  border: "1px solid #ffb020",
  borderRadius: 2,
  fontFamily: "var(--font-plexmono)",
  fontSize: 12,
  color: "#e8e4d6",
} as const;

const TICK_STYLE = { fontFamily: "var(--font-plexmono)", fontSize: 12 } as const;

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

  const serie = data?.resultats ?? [];
  const perimetre = communeChoisie ? communeChoisie.nom_commune : "Alpes-Maritimes";

  return (
    <div className="pt-8">
      <TitreSection
        sur="Tendances"
        titre={`Prix et volumes trimestriels — ${perimetre}`}
        sousTitre="20 trimestres d'historique DVF. Tape un nom de commune pour zoomer sur son marché."
      />
      <div className="mb-6 flex flex-wrap items-center gap-3">
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
        <div className="grid gap-6">
          <Reveal>
            <div className="glass px-4 py-6 sm:px-6">
              <h3 className="label-mono mb-4">Prix médian au m²</h3>
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={serie} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradPrix" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ffb020" stopOpacity={0.16} />
                      <stop offset="100%" stopColor="#ffb020" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(232,228,214,0.08)" vertical={false} />
                  <XAxis dataKey="trimestre" stroke="#8a8574" tickLine={false}
                         axisLine={{ stroke: "#e8e4d6" }} interval={3} tick={TICK_STYLE} />
                  <YAxis stroke="#8a8574" tickLine={false} axisLine={false} tick={TICK_STYLE}
                         domain={["dataMin - 300", "dataMax + 300"]}
                         tickFormatter={(v: number) => `${Math.round(v / 100) / 10}k`} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(v: number) => [euro(v) + "/m²", "Prix médian"]}
                  />
                  <Area type="monotone" dataKey="prix_m2_median" stroke="#ffb020" strokeWidth={2.5}
                        fill="url(#gradPrix)" animationDuration={700} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Reveal>
          <Reveal delay={0.08}>
            <div className="glass px-4 py-6 sm:px-6">
              <h3 className="label-mono mb-4">Volume de ventes</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={serie} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(232,228,214,0.08)" vertical={false} />
                  <XAxis dataKey="trimestre" stroke="#8a8574" tickLine={false}
                         axisLine={{ stroke: "#e8e4d6" }} interval={3} tick={TICK_STYLE} />
                  <YAxis stroke="#8a8574" tickLine={false} axisLine={false} tick={TICK_STYLE} />
                  <Tooltip
                    cursor={{ fill: "rgba(232,228,214,0.05)" }}
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(v: number) => [nombre(v), "Ventes"]}
                  />
                  <Bar dataKey="nb_ventes" fill="#e8e4d6" radius={0} animationDuration={700} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Reveal>
        </div>
      )}
    </div>
  );
}
