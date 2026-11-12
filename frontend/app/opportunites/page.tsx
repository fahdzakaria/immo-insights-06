"use client";

/** Vue Opportunités : classement par score composite, avec décomposition. */

import { motion } from "framer-motion";
import { useState } from "react";
import { Curseur, ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, TitreSection } from "@/components/ui";
import type { Opportunite, TypeBien } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, nombre, pct } from "@/lib/format";

const COMPOSANTES: { cle: keyof Opportunite; label: string; poids: string }[] = [
  { cle: "score_rendement", label: "Rendement", poids: "25 %" },
  { cle: "score_prix", label: "Prix accessible", poids: "20 %" },
  { cle: "score_dynamique_marche", label: "Marché en hausse", poids: "20 %" },
  { cle: "score_services", label: "Services à 500 m", poids: "15 %" },
  { cle: "score_dynamique_demo", label: "Démographie", poids: "10 %" },
  { cle: "score_tension", label: "Tension (vacance)", poids: "10 %" },
];

function AnneauScore({ score }: { score: number }) {
  const r = 26, c = 2 * Math.PI * r;
  return (
    <div className="relative h-16 w-16 shrink-0">
      <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="rgba(232,228,214,0.12)" strokeWidth="6" />
        <motion.circle
          cx="32" cy="32" r={r} fill="none" strokeWidth="6" strokeLinecap="butt"
          stroke={score >= 65 ? "#45d08c" : score >= 45 ? "#ffb020" : "#8a8574"}
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          whileInView={{ strokeDashoffset: c * (1 - score / 100) }}
          viewport={{ once: true }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </svg>
      <div className="tabular absolute inset-0 flex items-center justify-center font-display text-lg font-black">
        {score}
      </div>
    </div>
  );
}

export default function PageOpportunites() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [scoreMin, setScoreMin] = useState(50);
  const [prixMax, setPrixMax] = useState(10000);
  // Par défaut on écarte les communes dont le rendement repose sur un loyer extrapolé
  const [loyerFiable, setLoyerFiable] = useState(true);

  const { data, erreur } = useApi<{ resultats: Opportunite[] }>("/api/v1/opportunites", {
    departement: "06",
    type_bien: typeBien,
    score_min: scoreMin,
    prix_m2_max: prixMax < 10000 ? prixMax : undefined,
    loyer_fiable: loyerFiable || undefined,
    limit: 30,
  });

  return (
    <div className="pt-8">
      <TitreSection
        sur="Opportunités"
        titre="Où investir dans le 06, selon la donnée"
        sousTitre="Score 0-100 croisant prix bas, rendement, marché en hausse, démographie, services et tension locative — en centiles départementaux, communes à ≥ 20 ventes/24 mois. Le rendement pèse 25 % du score : par défaut, seules les communes dont le loyer est mesuré localement sont affichées."
      />
      <div className="glass mb-8 flex flex-wrap items-end gap-6 px-5 py-4">
        <ToggleTypeBien valeur={typeBien} onChange={(t) => t && setTypeBien(t)} />
        <div className="w-52">
          <Curseur label="Score minimum" valeur={scoreMin} onChange={setScoreMin} min={0} max={80} pas={5} />
        </div>
        <div className="w-52">
          <Curseur label="Prix max €/m²" valeur={prixMax} onChange={setPrixMax} min={1000} max={10000} pas={250}
                   format={(v) => (v >= 10000 ? "sans limite" : euro(v))} />
        </div>
        <button
          onClick={() => setLoyerFiable((v) => !v)}
          aria-pressed={loyerFiable}
          title="Loyer prédit à l'échelle de la commune (assez d'annonces locales). Décoché : inclut les communes au loyer extrapolé d'une zone plus large."
          className={`label-mono cursor-pointer border border-ink px-4 py-2 transition-colors ${
            loyerFiable ? "bg-ink !text-bg" : "hover:bg-ink/5"}`}
        >
          {loyerFiable ? "✓ " : ""}Loyers fiables seulement
        </button>
        <span className="ml-auto text-sm text-muted">{data?.resultats.length ?? "…"} communes</span>
      </div>

      {erreur && <Erreur message={erreur} />}
      {!erreur && !data && <Chargement />}
      {data?.resultats.length === 0 && (
        <div className="glass px-6 py-12 text-center text-muted">
          Aucune commune ne passe ces filtres — baisse le score minimum{loyerFiable ? " ou décoche « loyers fiables seulement »" : ""}.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {data?.resultats.map((o, i) => (
          <motion.div
            key={o.code_commune + o.type_bien}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: (i % 2) * 0.06 }}
            className="glass glass-hover px-5 py-5"
          >
            <div className="mb-4 flex items-center gap-4">
              <AnneauScore score={o.score_investissement} />
              <div className="min-w-0">
                <div className="truncate font-display text-lg font-bold">
                  <span className="mr-2 text-muted">#{i + 1}</span>{o.nom_commune}
                </div>
                <div className="text-sm text-muted">
                  {euro(o.prix_m2_median)}/m² · rendement {pct(o.rendement_brut_pct, false)}
                  {!o.rendement_fiable && (
                    <span title="Loyer extrapolé d'une zone plus large que la commune : rendement peu fiable" className="text-warn">*</span>
                  )} ·{" "}
                  {nombre(o.nb_ventes_24m)} ventes 24 m
                </div>
              </div>
              <div className={`ml-auto text-right text-sm font-semibold ${
                (o.evolution_3ans_pct ?? 0) >= 0 ? "text-good" : "text-bad"}`}>
                {pct(o.evolution_3ans_pct)}
                <div className="text-xs font-normal text-muted">sur 3 ans</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {COMPOSANTES.map((comp) => (
                <div key={comp.cle} className="text-xs">
                  <div className="mb-1 flex justify-between text-muted">
                    <span>{comp.label}</span>
                    <span className="tabular" title={`poids ${comp.poids}`}>{Number(o[comp.cle] ?? 0)}</span>
                  </div>
                  <div className="h-1.5 bg-ink/10">
                    <motion.div
                      className="h-full bg-accent"
                      initial={{ width: 0 }}
                      whileInView={{ width: `${Number(o[comp.cle] ?? 0)}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.7, delay: 0.15 }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
