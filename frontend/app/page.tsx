"use client";

/** Une de l'observatoire : maquette 3D interactive, KPIs, impact DPE. */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SurvolCommune } from "@/components/Hero3D";
import Ticker from "@/components/Ticker";
import { Chargement, Compteur, Erreur, Reveal, TitreSection } from "@/components/ui";
import type { CommunePrix, ImpactDpe, Kpis } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { DPE_COULEURS, euro, evolClass, nombre, pct } from "@/lib/format";

const Hero3D = dynamic(() => import("@/components/Hero3D"), { ssr: false });

const TOOLTIP_STYLE = {
  background: "#14140f",
  border: "1px solid #ffb020",
  borderRadius: 2,
  fontFamily: "var(--font-plexmono)",
  fontSize: 12,
  color: "#e8e4d6",
} as const;

export default function PageMarche() {
  const [survol, setSurvol] = useState<SurvolCommune | null>(null);
  const posSouris = useRef({ x: 0, y: 0 });
  const etiquette = useRef<HTMLDivElement>(null);

  const { data: kpis, erreur } = useApi<Kpis>("/api/v1/kpis", { departement: "06" });
  const { data: communes } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: "appartement", limit: 500,
  });
  const { data: dpe } = useApi<{ resultats: ImpactDpe[] }>("/api/v1/dpe/impact", {
    departement: "06", type_bien: "appartement",
  });

  const appart = kpis?.par_type_bien.find((t) => t.type_bien === "appartement");
  const maison = kpis?.par_type_bien.find((t) => t.type_bien === "maison");
  const evoAppart = kpis?.evolutions.find((t) => t.type_bien === "appartement");

  return (
    <div>
      {/* ---------- UNE : maquette 3D interactive ---------- */}
      <section
        className="relative -mx-4 h-[80vh] min-h-[540px] overflow-hidden border-b-2 border-ink sm:-mx-6"
        onPointerMove={(e) => {
          posSouris.current = { x: e.clientX, y: e.clientY };
          if (etiquette.current) {
            etiquette.current.style.left = `${e.clientX + 16}px`;
            etiquette.current.style.top = `${e.clientY - 12}px`;
          }
        }}
      >
        <div className="absolute inset-0">
          {communes ? <Hero3D communes={communes.resultats} onSurvol={setSurvol} /> : null}
        </div>
        {/* Voile charbon : garde le texte lisible sans masquer la maquette à droite */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-bg via-bg/60 to-transparent sm:w-2/3" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-bg/85 to-transparent" />

        {/* Étiquette de survol 3D, façon relevé d'arpenteur */}
        {survol && (
          <div
            ref={etiquette}
            className="pointer-events-none fixed z-50 border border-ink bg-panel px-3 py-2 shadow-[4px_4px_0_rgba(232,228,214,0.15)]"
            style={{ left: posSouris.current.x + 16, top: posSouris.current.y - 12 }}
          >
            <div className="font-display text-sm font-black">{survol.nom}</div>
            <div className="label-mono !text-accent2 tabular">{euro(survol.prix)}/m² médian</div>
          </div>
        )}

        <div className="pointer-events-none relative z-10 mx-auto flex h-full max-w-7xl flex-col justify-end px-4 pb-14 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="label-mono mb-4 flex items-center gap-3"
          >
            <span className="live-dot" />
            Observatoire du marché — Alpes-Maritimes ·{" "}
            {kpis ? `${kpis.periode[0]} → ${kpis.periode[1]}` : "2021 → 2025"}
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.12 }}
            className="max-w-4xl font-display text-4xl font-black leading-[1.02] tracking-tight sm:text-7xl"
          >
            La Côte d'Azur,
            <br />
            <span className="text-gradient">relevée au millimètre.</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.24 }}
            className="mt-5 max-w-xl leading-relaxed text-muted"
          >
            {kpis ? nombre(kpis.nb_ventes_total) : "128 600"} ventes réelles, {" "}
            {kpis?.nb_communes ?? 163} communes. Chaque barre de cette maquette est une commune —
            survole-la : sa hauteur, c'est son prix au m².
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.36 }}
            className="pointer-events-auto mt-8 flex flex-wrap gap-3"
          >
            <Link
              href="/carte"
              className="label-mono border border-accent bg-accent px-6 py-3 !text-bg font-medium transition-colors hover:bg-[#ffc44d]"
            >
              Explorer la carte →
            </Link>
            <Link
              href="/opportunites"
              className="label-mono border border-ink bg-panel px-6 py-3 !text-ink transition-colors hover:bg-ink hover:!text-bg"
            >
              Les opportunités
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ---------- TICKER ---------- */}
      {communes && <Ticker communes={communes.resultats} />}

      {erreur && <Erreur message={erreur} />}

      {/* ---------- KPIs ---------- */}
      <section className="mt-16">
        <TitreSection
          sur="01 — Vue d'ensemble"
          titre="Le 06 en quatre chiffres"
          sousTitre="Calculés sur les 12 derniers mois de transactions, recalculés chaque matin par le pipeline."
        />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            {
              label: "ventes analysées",
              contenu: kpis && <Compteur valeur={kpis.nb_ventes_total} className="tabular text-3xl font-black sm:text-4xl" />,
              detail: `${kpis?.nb_communes ?? "—"} communes`,
            },
            {
              label: "appartement · médiane 12 m",
              contenu: appart && (
                <Compteur valeur={appart.prix_m2_median_12m} suffixe=" €/m²" className="tabular text-3xl font-black sm:text-4xl" />
              ),
              detail: `${nombre(appart?.nb_ventes_12m)} ventes 12 m`,
            },
            {
              label: "maison · médiane 12 m",
              contenu: maison && (
                <Compteur valeur={maison.prix_m2_median_12m} suffixe=" €/m²" className="tabular text-3xl font-black sm:text-4xl" />
              ),
              detail: `${nombre(maison?.nb_ventes_12m)} ventes 12 m`,
            },
            {
              label: "rendement brut médian",
              contenu: kpis && (
                <Compteur valeur={kpis.rendement_brut_median} decimales={2} suffixe=" %" className="tabular text-3xl font-black sm:text-4xl" />
              ),
              detail: evoAppart ? `appart : ${pct(evoAppart.evolution_1an_pct_mediane)} sur 1 an` : "",
              detailClass: evolClass(evoAppart?.evolution_1an_pct_mediane),
            },
          ].map((kpi, i) => (
            <Reveal key={kpi.label} delay={i * 0.08}>
              <div className="glass glass-hover flex h-full flex-col gap-2 px-5 py-6">
                <div className="text-accent">{kpi.contenu ?? <Chargement texte="" />}</div>
                <div className="label-mono">{kpi.label}</div>
                <div className={`mt-auto pt-1 text-sm ${kpi.detailClass ?? "text-muted"}`}>{kpi.detail}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------- IMPACT DPE ---------- */}
      <section className="mt-20">
        <TitreSection
          sur="02 — Énergie"
          titre="Ce que l'étiquette DPE fait au prix"
          sousTitre="Écart médian de prix par rapport à un logement comparable (même commune, même année, même type de bien, DPE connu). Écart observé, pas l'effet de l'énergie seule : les étiquettes A et B sont surtout des logements récents."
        />
        <Reveal>
          <div className="glass px-4 py-6 sm:px-6">
            {dpe ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={dpe.resultats} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(232,228,214,0.08)" vertical={false} />
                  <XAxis dataKey="etiquette_dpe" stroke="#8a8574" tickLine={false} axisLine={{ stroke: "#e8e4d6" }}
                         tick={{ fontFamily: "var(--font-plexmono)", fontSize: 12 }} />
                  <YAxis stroke="#8a8574" tickLine={false} axisLine={false} unit=" %"
                         tick={{ fontFamily: "var(--font-plexmono)", fontSize: 12 }} />
                  <Tooltip
                    cursor={{ fill: "rgba(232,228,214,0.05)" }}
                    contentStyle={TOOLTIP_STYLE}
                    itemStyle={{ color: "#e8e4d6" }}
                    labelStyle={{ color: "#8a8574" }}
                    formatter={(v: number, _n, item) => [
                      `${v > 0 ? "+" : ""}${v} % ± ${item.payload.ecart_ic95_pct} vs logement comparable (${nombre(item.payload.nb_ventes)} ventes${item.payload.fiable ? "" : ", écart non significatif"})`,
                      `Étiquette ${item.payload.etiquette_dpe}`,
                    ]}
                  />
                  <Bar dataKey="ecart_vs_marche_pct" radius={0}>
                    {dpe.resultats.map((d) => (
                      <Cell key={d.etiquette_dpe} fill={DPE_COULEURS[d.etiquette_dpe]} stroke="#0c0c0a" strokeWidth={0.5}
                            fillOpacity={d.fiable ? 1 : 0.35} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Chargement />
            )}
          </div>
        </Reveal>
      </section>

      {/* ---------- PIPELINE ---------- */}
      <section className="mt-20">
        <TitreSection sur="03 — Sous le capot" titre="Un vrai pipeline data, pas un tableau Excel" />
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ["Ingestion", "5 sources publiques (DVF, INSEE, ADEME, loyers, OSM) ingérées chaque matin par Airflow, en Parquet idempotent."],
            ["Qualité", "9 règles de nettoyage documentées, géocodage BAN, 32 tests dbt + 45 tests Python — chaque chiffre est traçable."],
            ["Marts", "dbt agrège 128 600 ventes en marts DuckDB pré-calculés : chaque filtre de ce site répond en quelques millisecondes."],
          ].map(([titre, texte], i) => (
            <Reveal key={titre} delay={i * 0.1}>
              <div className="glass glass-hover h-full px-5 py-6">
                <div className="label-mono mb-3 !text-accent">0{i + 1} — {titre}</div>
                <p className="text-sm leading-relaxed text-muted">{texte}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  );
}
