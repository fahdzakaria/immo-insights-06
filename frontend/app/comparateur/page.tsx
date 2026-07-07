"use client";

/** Vue Comparateur : jusqu'à 3 communes côte à côte + radar des 6 composantes du score. */

import { useState } from "react";
import {
  PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip,
} from "recharts";
import { ChampRecherche } from "@/components/filtres";
import { Erreur, Reveal, TitreSection } from "@/components/ui";
import type { CommunePrix, DetailCommune } from "@/lib/api";
import { apiGet } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, evolClass, nombre, pct } from "@/lib/format";

// Trois encres d'imprimeur : bleu Klein, terracotta, vert anglais
const COULEURS = ["#ffb020", "#ff6b57", "#45d08c"];

const AXES: { cle: keyof NonNullable<DetailCommune["scores"][number]>; label: string }[] = [
  { cle: "score_prix", label: "Prix" },
  { cle: "score_rendement", label: "Rendement" },
  { cle: "score_dynamique_marche", label: "Marché" },
  { cle: "score_dynamique_demo", label: "Démographie" },
  { cle: "score_services", label: "Services" },
  { cle: "score_tension", label: "Tension" },
];

export default function PageComparateur() {
  const [recherche, setRecherche] = useState("");
  const [selection, setSelection] = useState<DetailCommune[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);

  const { data: communes } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: "appartement", limit: 500,
  });

  async function ajouter(nom: string) {
    const c = communes?.resultats.find((x) => x.nom_commune.toLowerCase() === nom.toLowerCase());
    if (!c || selection.some((s) => s.code_commune === c.code_commune) || selection.length >= 3) return;
    try {
      const detail = await apiGet<DetailCommune>(`/api/v1/communes/${c.code_commune}`);
      setSelection((s) => [...s, detail]);
      setRecherche("");
      setErreur(null);
    } catch (e) {
      setErreur((e as Error).message);
    }
  }

  const donneesRadar = AXES.map((axe) => {
    const ligne: Record<string, string | number> = { axe: axe.label };
    selection.forEach((c) => {
      const score = c.scores.find((s) => s.type_bien === "appartement") ?? c.scores[0];
      ligne[c.nom_commune] = score ? Number(score[axe.cle] ?? 0) : 0;
    });
    return ligne;
  });

  return (
    <div className="pt-8">
      <TitreSection
        sur="Comparateur"
        titre="Trois communes, face à face"
        sousTitre="Prix, évolution, rendement et les six composantes du score d'investissement."
      />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <ChampRecherche
          valeur={recherche}
          onChange={(v) => { setRecherche(v); ajouter(v); }}
          liste={communes?.resultats.map((c) => c.nom_commune) ?? []}
          listeId="communes-comparateur"
          placeholder="Ajouter une commune…"
        />
        {selection.map((c, i) => (
          <button
            key={c.code_commune}
            onClick={() => setSelection((s) => s.filter((x) => x.code_commune !== c.code_commune))}
            className="label-mono cursor-pointer border border-ink bg-panel px-3.5 py-2 transition-colors hover:bg-bad/10"
            style={{ color: COULEURS[i] }}
          >
            {c.nom_commune} ✕
          </button>
        ))}
      </div>
      {erreur && <Erreur message={erreur} />}

      {selection.length === 0 && (
        <div className="glass px-6 py-14 text-center text-muted">
          Ajoute une commune pour commencer — par exemple <em>Nice</em>, <em>Grasse</em> ou <em>Drap</em>.
        </div>
      )}

      {selection.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Cartes chiffres */}
          <div className="grid gap-4">
            {selection.map((c, i) => {
              const appart = c.prix.find((p) => p.type_bien === "appartement") ?? c.prix[0];
              const rdt = c.rendement.find((r) => r.type_bien === appart?.type_bien);
              const score = c.scores.find((s) => s.type_bien === appart?.type_bien);
              return (
                <Reveal key={c.code_commune} delay={i * 0.07}>
                  <div className="glass glass-hover px-5 py-5">
                    <div className="mb-3 flex items-baseline justify-between">
                      <h3 className="font-display text-xl font-bold" style={{ color: COULEURS[i] }}>
                        {c.nom_commune}
                      </h3>
                      {score && (
                        <span className="label-mono border border-ink px-2.5 py-1 !text-ink tabular">
                          {score.score_investissement}/100
                        </span>
                      )}
                    </div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                      <div><dt className="text-muted">Prix médian</dt>
                        <dd className="font-semibold">{appart?.prix_m2_median ? euro(appart.prix_m2_median) + "/m²" : "—"}</dd></div>
                      <div><dt className="text-muted">Évol. 1 an</dt>
                        <dd className={`font-semibold ${evolClass(appart?.evolution_1an_pct)}`}>{pct(appart?.evolution_1an_pct)}</dd></div>
                      <div><dt className="text-muted">Rendement</dt>
                        <dd className="font-semibold">{pct(rdt?.rendement_brut_pct, false)}</dd></div>
                      <div><dt className="text-muted">Ventes 24 m</dt>
                        <dd className="font-semibold">{nombre(appart?.nb_ventes_24m)}</dd></div>
                    </dl>
                  </div>
                </Reveal>
              );
            })}
          </div>

          {/* Radar */}
          <Reveal delay={0.1}>
            <div className="glass flex h-full min-h-[380px] flex-col px-4 py-6">
              <h3 className="label-mono mb-2 px-2">
                Profil d'investissement (centiles départementaux)
              </h3>
              <ResponsiveContainer width="100%" height={360}>
                <RadarChart data={donneesRadar} outerRadius="72%">
                  <PolarGrid stroke="rgba(232,228,214,0.15)" />
                  <PolarAngleAxis dataKey="axe" tick={{ fill: "#8a8574", fontSize: 12, fontFamily: "var(--font-plexmono)" }} />
                  <Tooltip contentStyle={{ background: "#14140f", border: "1px solid #ffb020", borderRadius: 2,
                                           fontFamily: "var(--font-plexmono)", fontSize: 12, color: "#e8e4d6" }} />
                  {selection.map((c, i) => (
                    <Radar key={c.code_commune} name={c.nom_commune} dataKey={c.nom_commune}
                           stroke={COULEURS[i]} fill={COULEURS[i]} fillOpacity={0.18} strokeWidth={2} />
                  ))}
                </RadarChart>
              </ResponsiveContainer>
              <p className="label-mono px-2">
                Radar disponible pour les communes à ≥ 20 ventes/24 mois (sinon axes à zéro).
              </p>
            </div>
          </Reveal>
        </div>
      )}
    </div>
  );
}
