"use client";

/** Une de l'observatoire : hero en verre cannelé + aperçu de la vraie carte,
 *  chiffres clés, ce que dit la carte (visuels tirés des vrais contours),
 *  impact DPE, méthode. */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ApercuCarte from "@/components/ApercuCarte";
import HeroShader from "@/components/HeroShader";
import Ticker from "@/components/Ticker";
import { Chargement, Compteur, Erreur, Reveal, TitreSection } from "@/components/ui";
import VisuelForme, { type Texture } from "@/components/VisuelForme";
import type { CommunePrix, ImpactDpe, Kpis, QuartierPrix } from "@/lib/api";
import { SEUIL_VENTES_AFFICHAGE } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { DPE_COULEURS, euro, evolClass, nombre, pct } from "@/lib/format";
import type { Geometrie } from "@/lib/geo";
import { couleurPrix, seuilsPrix } from "@/lib/palette";

const TOOLTIP_STYLE = {
  background: "#0a0a0a",
  border: "1px solid #2e2e2e",
  borderRadius: 12,
  fontFamily: "var(--font-geistmono)",
  fontSize: 12,
  color: "#f2efe9",
} as const;

const LITTORAL = ["Nice", "Cannes", "Antibes", "Cagnes-sur-Mer", "Menton", "Le Cannet", "Mandelieu-la-Napoule", "Villefranche-sur-Mer"];

/** Charge un GeoJSON statique une seule fois. */
function useGeo(url: string) {
  const [geo, setGeo] = useState<GeoJSON.FeatureCollection | null>(null);
  useEffect(() => {
    let actif = true;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((g) => actif && setGeo(g))
      .catch(() => {});
    return () => {
      actif = false;
    };
  }, [url]);
  return geo;
}

interface Fiche {
  cle: string;
  sur: string;
  geometrie: Geometrie;
  couleur: string;
  texture: Texture;
  legende: [string, string];
  grand: React.ReactNode;
  titre: string;
  texte: React.ReactNode;
  puces: { texte: string; classe?: string }[];
}

// Lignes du bloc « code » : [type, clé, opérateur, valeur, commentaire]
const ONGLETS: Record<string, string[][]> = {
  "Règles": [
    ["c", "// règles appliquées à chaque chiffre du site"],
    ["k", "afficher_prix", " si ventes_24_mois ≥ ", String(SEUIL_VENTES_AFFICHAGE), "    // sinon : zone éteinte, aucun prix"],
    ["k", "agrégat", "       = ", "\"médiane\"", "          // pas la moyenne : insensible aux ventes extrêmes"],
    ["k", "fenêtre", "       = ", "\"24 mois\"", "          // glissante, recalculée à chaque publication"],
    ["k", "fiable", "        = ventes ≥ ", "20", "         // en dessous : chiffre affiché mais signalé"],
    ["k", "dpe", "           = ", "\"écart observé\"", "    // à logement comparable, pas un effet causal"],
  ],
  Sources: [
    ["c", "// données publiques, ingérées sans retouche"],
    ["k", "ventes", "    = ", "\"DVF — DGFiP / Etalab\"", "   // actes notariés, depuis 2021"],
    ["k", "quartiers", " = ", "\"INSEE — contours IRIS\"", ""],
    ["k", "énergie", "   = ", "\"ADEME — DPE logements\"", ""],
    ["k", "loyers", "    = ", "\"Carte des loyers\"", "       // rendement, à la commune seulement"],
    ["k", "contexte", "  = ", "\"OpenStreetMap\"", ""],
  ],
  Pipeline: [
    ["c", "// chaque lundi, reconstruit de zéro sur GitHub Actions"],
    ["k", "ingestion", "   = ", "\"Airflow → Parquet\"", "        // 5 sources, idempotent"],
    ["k", "qualité", "     = ", "\"géocodage BAN + tests\"", "    // dbt et pytest : chiffres traçables"],
    ["k", "marts", "       = ", "\"dbt + DuckDB\"", "             // pré-agrégés : filtres instantanés"],
    ["k", "publication", " = ", "\"JSON statique → Vercel\"", ""],
  ],
};

const apparition = (delai: number) => ({
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.6, delay: delai, ease: [0.21, 0.65, 0.32, 1] as [number, number, number, number] },
});

export default function PageMarche() {
  const [onglet, setOnglet] = useState("Règles");

  const { data: kpis, erreur } = useApi<Kpis>("/api/v1/kpis", { departement: "06" });
  const { data: communes } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: "appartement", limit: 500,
  });
  const { data: quartiers } = useApi<{ resultats: QuartierPrix[] }>("/api/v1/quartiers", {
    departement: "06", type_bien: "appartement", limit: 2000,
  });
  const { data: dpe } = useApi<{ resultats: ImpactDpe[] }>("/api/v1/dpe/impact", {
    departement: "06", type_bien: "appartement",
  });
  const geoCommunes = useGeo("/geo/communes-06.geojson");
  const geoQuartiers = useGeo("/geo/iris-06.geojson");

  const appart = kpis?.par_type_bien.find((t) => t.type_bien === "appartement");
  const maison = kpis?.par_type_bien.find((t) => t.type_bien === "maison");
  const evoAppart = kpis?.evolutions.find((t) => t.type_bien === "appartement");

  // Même échelle que la page Carte : quantiles sur communes (≥ 5 ventes) + quartiers
  const seuils = useMemo(() => {
    if (!communes || !quartiers) return null;
    const vals = [
      ...communes.resultats.filter((c) => (c.nb_ventes_24m ?? 0) >= SEUIL_VENTES_AFFICHAGE).map((c) => c.prix_m2_median),
      ...quartiers.resultats.map((q) => q.prix_m2_median),
    ].filter((v): v is number => v != null);
    return seuilsPrix(vals);
  }, [communes, quartiers]);

  const fiches: Fiche[] | null = useMemo(() => {
    if (!communes || !quartiers || !geoCommunes || !geoQuartiers || !seuils) return null;
    const geomQ = new Map(geoQuartiers.features.map((f) => [String(f.properties?.code), f.geometry as Geometrie]));
    const geomC = new Map(geoCommunes.features.map((f) => [String(f.properties?.code), f.geometry as Geometrie]));
    const qs = quartiers.resultats.filter((q) => q.prix_m2_median != null && q.fiable && geomQ.has(q.code_iris));
    const cs = communes.resultats.filter(
      (c) => c.prix_m2_median != null && (c.nb_ventes_24m ?? 0) >= SEUIL_VENTES_AFFICHAGE && geomC.has(c.code_commune),
    );
    const sortie: Fiche[] = [];
    const petit = (t: string) => <small className="ml-1.5 font-sans text-base text-muted">{t}</small>;

    const cher = [...qs].sort((a, b) => b.prix_m2_median! - a.prix_m2_median!)[0];
    if (cher)
      sortie.push({
        cle: "cher", sur: "Quartier le plus cher", geometrie: geomQ.get(cher.code_iris)!,
        couleur: couleurPrix(cher.prix_m2_median, seuils), texture: "trame",
        legende: [`${cher.nom_commune}, ${cher.nom_iris}`, "quartier · contour réel"],
        grand: <>{euro(cher.prix_m2_median)}{petit("/m²")}</>,
        titre: cher.nom_iris,
        texte: <>{cher.nom_commune}, sur <b className="font-medium text-ink">{nombre(cher.nb_ventes_24m)} ventes</b> en 24 mois ; la commune est à {euro(cher.prix_m2_median_commune)}/m².</>,
        puces: [{ texte: `${nombre(cher.nb_ventes_24m)} ventes` }, { texte: `${pct(cher.ecart_commune_pct)} vs commune` }],
      });

    const hausse = qs
      .filter((q) => q.nb_ventes_24m >= 30 && q.evolution_1an_pct != null)
      .sort((a, b) => b.evolution_1an_pct! - a.evolution_1an_pct!)[0];
    if (hausse)
      sortie.push({
        cle: "hausse", sur: "Plus forte hausse sur 1 an", geometrie: geomQ.get(hausse.code_iris)!,
        couleur: couleurPrix(hausse.prix_m2_median, seuils), texture: "cannele",
        legende: [`${hausse.nom_commune}, ${hausse.nom_iris}`, "quartier · contour réel"],
        grand: <span className="text-good">{pct(hausse.evolution_1an_pct)}</span>,
        titre: hausse.nom_iris,
        texte: <>{hausse.nom_commune}, {euro(hausse.prix_m2_median)}/m². Parmi les quartiers d’au moins 30 ventes.</>,
        puces: [{ texte: `${nombre(hausse.nb_ventes_24m)} ventes` }, { texte: `${euro(hausse.prix_m2_median)}/m²` }],
      });

    const abordable = cs
      .filter((c) => LITTORAL.includes(c.nom_commune))
      .sort((a, b) => a.prix_m2_median! - b.prix_m2_median!)[0];
    if (abordable)
      sortie.push({
        cle: "abordable", sur: "Littoral le plus abordable", geometrie: geomC.get(abordable.code_commune)!,
        couleur: couleurPrix(abordable.prix_m2_median, seuils), texture: "pixels",
        legende: [`${abordable.nom_commune}, commune`, "littoral · contour réel"],
        grand: <>{euro(abordable.prix_m2_median)}{petit("/m²")}</>,
        titre: abordable.nom_commune,
        texte: <>La moins chère de huit grandes communes du littoral, sur {nombre(abordable.nb_ventes_24m)} ventes en 24 mois.</>,
        puces: [
          { texte: `${nombre(abordable.nb_ventes_24m)} ventes` },
          ...(abordable.evolution_1an_pct != null
            ? [{ texte: `${pct(abordable.evolution_1an_pct)} sur 1 an`, classe: evolClass(abordable.evolution_1an_pct) }]
            : []),
        ],
      });

    const actif = [...cs].sort((a, b) => (b.nb_ventes_24m ?? 0) - (a.nb_ventes_24m ?? 0))[0];
    if (actif)
      sortie.push({
        cle: "actif", sur: "Marché le plus actif", geometrie: geomC.get(actif.code_commune)!,
        couleur: couleurPrix(actif.prix_m2_median, seuils), texture: "trame",
        legende: [`${actif.nom_commune}, commune`, "commune · contour réel"],
        grand: <>{nombre(actif.nb_ventes_24m)}{petit("ventes")}</>,
        titre: actif.nom_commune,
        texte: <>Première commune du département en nombre de ventes sur 24 mois, à {euro(actif.prix_m2_median)}/m².</>,
        puces: [
          { texte: `${euro(actif.prix_m2_median)}/m²` },
          ...(actif.evolution_1an_pct != null
            ? [{ texte: `${pct(actif.evolution_1an_pct)} sur 1 an`, classe: evolClass(actif.evolution_1an_pct) }]
            : []),
        ],
      });
    return sortie;
  }, [communes, quartiers, geoCommunes, geoQuartiers, seuils]);

  return (
    <div>
      {/* ---------- HERO : verre cannelé + aperçu de la vraie carte ---------- */}
      <section className="relative -mx-4 overflow-hidden border-b border-line sm:-mx-6">
        <HeroShader className="absolute inset-0 h-full w-full" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black via-black/70 to-black/5" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black to-transparent" />
        {/* En une colonne, le texte passe devant la lueur : voile plus dense */}
        <div className="pointer-events-none absolute inset-0 bg-black/45 lg:hidden" />

        <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-4 pb-20 pt-20 sm:px-6 lg:min-h-[calc(100svh-4rem-3.25rem)] lg:grid-cols-[1.05fr_.95fr] lg:gap-16 lg:py-24">
          <div>
            <motion.div {...apparition(0)}>
              <Link href="/carte" className="pastille">
                Nouveau : les prix par quartier
                <span className="text-muted">›</span>
              </Link>
            </motion.div>
            <motion.h1 {...apparition(0.08)} className="mt-7 font-display text-[2.6rem] leading-[1.02] sm:text-6xl lg:text-[4.25rem]">
              <span className="titre-degrade">La Côte d’Azur,</span>
              <br />
              <span className="text-gradient">au mètre carré près</span>
            </motion.h1>
            <motion.p {...apparition(0.16)} className="mt-6 max-w-lg text-lg leading-relaxed text-muted">
              {kpis ? nombre(kpis.nb_ventes_total) : "128 600"} ventes notariales, {kpis?.nb_communes ?? 163} communes,{" "}
              {geoQuartiers ? nombre(geoQuartiers.features.length) : "364"} quartiers. Mis à jour chaque lundi.
            </motion.p>
            <motion.div {...apparition(0.24)} className="mt-9 flex flex-wrap items-center gap-3">
              <Link href="/carte" className="btn btn-clair">
                Explorer la carte
              </Link>
              <Link href="/opportunites" className="btn text-muted hover:text-ink">
                Les opportunités <span aria-hidden>›</span>
              </Link>
            </motion.div>
          </div>

          <motion.div {...apparition(0.3)}>
            {geoCommunes && communes && seuils ? (
              <ApercuCarte geo={geoCommunes} communes={communes.resultats} seuils={seuils} />
            ) : (
              <div className="glass flex aspect-[640/480] items-center justify-center !rounded-[20px]">
                <Chargement texte="Chargement de la carte…" />
              </div>
            )}
          </motion.div>
        </div>
        {communes && (
          <div className="relative">
            <Ticker communes={communes.resultats} />
          </div>
        )}
      </section>

      {erreur && <Erreur message={erreur} />}

      {/* ---------- CHIFFRES CLÉS ---------- */}
      <section className="pt-20 sm:pt-28">
        <TitreSection
          sur="Vue d'ensemble"
          titre="Le 06 en quatre chiffres"
          sousTitre="Médianes sur les 12 derniers mois de transactions ; total des ventes depuis 2021. Recalculés à chaque publication du lundi."
        />
        <div className="grid grid-cols-2 gap-4 sm:gap-5 lg:grid-cols-4">
          {[
            {
              label: "ventes analysées",
              contenu: kpis && <Compteur valeur={kpis.nb_ventes_total} className="tabular" />,
              detail: `${kpis?.nb_communes ?? "—"} communes`,
            },
            {
              label: "appartement · médiane 12 mois",
              contenu: appart && <Compteur valeur={appart.prix_m2_median_12m} suffixe=" €/m²" className="tabular" />,
              detail: `${nombre(appart?.nb_ventes_12m)} ventes sur 12 mois`,
            },
            {
              label: "maison · médiane 12 mois",
              contenu: maison && <Compteur valeur={maison.prix_m2_median_12m} suffixe=" €/m²" className="tabular" />,
              detail: `${nombre(maison?.nb_ventes_12m)} ventes sur 12 mois`,
            },
            {
              label: "rendement brut médian",
              contenu: kpis && <Compteur valeur={kpis.rendement_brut_median} decimales={2} suffixe=" %" className="tabular" />,
              detail: evoAppart ? `appartement : ${pct(evoAppart.evolution_1an_pct_mediane)} sur 1 an` : "",
              detailClass: evolClass(evoAppart?.evolution_1an_pct_mediane),
            },
          ].map((kpi, i) => (
            <Reveal key={kpi.label} delay={i * 0.06}>
              <div className="glass glass-hover flex h-full flex-col gap-3 px-6 py-7">
                <div className="label-mono">{kpi.label}</div>
                <div className="whitespace-nowrap font-display text-[1.65rem] text-ink sm:text-3xl xl:text-4xl">{kpi.contenu ?? <Chargement texte="" />}</div>
                <div className={`mt-auto pt-1 text-sm ${kpi.detailClass ?? "text-muted"}`}>{kpi.detail}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------- CE QUE DIT LA CARTE ---------- */}
      <section className="pt-20 sm:pt-28">
        <TitreSection
          sur="Ce que dit la carte"
          titre="Quatre lectures, quatre vrais contours"
          sousTitre="Chaque visuel est la forme exacte du quartier ou de la commune, dans la couleur de son prix sur la carte. Aucune image décorative."
        />
        {fiches ? (
          <div className="grid gap-5 sm:grid-cols-2 sm:gap-6">
            {fiches.map((f, i) => (
              <Reveal key={f.cle} delay={(i % 2) * 0.06}>
                <article className="glass glass-hover flex h-full flex-col overflow-hidden p-1.5">
                  <div className="relative aspect-[16/8] overflow-hidden rounded-[11px] bg-black">
                    <VisuelForme geometrie={f.geometrie} couleur={f.couleur} texture={f.texture} graine={i + 3} label={`Contour de ${f.titre}`} />
                    <p className="legende absolute bottom-3 left-3">
                      <b>{f.legende[0]}</b>
                      {f.legende[1]}
                    </p>
                  </div>
                  <div className="flex flex-1 flex-col px-5 pb-5 pt-6">
                    <div className="label-mono">{f.sur}</div>
                    <div className="tabular mt-3 font-display text-4xl leading-none">{f.grand}</div>
                    <h3 className="mt-2 font-display text-xl text-ink">{f.titre}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted">{f.texte}</p>
                    <div className="mt-auto flex flex-wrap gap-2 pt-4">
                      {f.puces.map((p) => (
                        <span key={p.texte} className={`rounded-full border border-line2 px-2.5 py-1 font-mono text-xs ${p.classe ?? "text-muted"}`}>
                          {p.texte}
                        </span>
                      ))}
                    </div>
                  </div>
                </article>
              </Reveal>
            ))}
          </div>
        ) : (
          <Chargement />
        )}
      </section>

      {/* ---------- IMPACT DPE ---------- */}
      <section className="pt-20 sm:pt-28">
        <TitreSection
          sur="Énergie"
          titre="Ce que l'étiquette DPE fait au prix"
          sousTitre="Écart médian de prix par rapport à un logement comparable (même commune, même année, même type de bien, DPE connu). Écart observé, pas l'effet de l'énergie seule : les étiquettes A et B sont surtout des logements récents."
        />
        <Reveal>
          <div className="glass px-4 py-6 sm:px-6">
            {dpe ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={dpe.resultats} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey="etiquette_dpe" stroke="#8f8c84" tickLine={false} axisLine={{ stroke: "#2e2e2e" }}
                         tick={{ fontFamily: "var(--font-geistmono)", fontSize: 12 }} />
                  <YAxis stroke="#8f8c84" tickLine={false} axisLine={false} unit=" %"
                         tick={{ fontFamily: "var(--font-geistmono)", fontSize: 12 }} />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    contentStyle={TOOLTIP_STYLE}
                    itemStyle={{ color: "#f2efe9" }}
                    labelStyle={{ color: "#8f8c84" }}
                    formatter={(v: number, _n, item) => [
                      `${v > 0 ? "+" : ""}${v} % ± ${item.payload.ecart_ic95_pct} vs logement comparable (${nombre(item.payload.nb_ventes)} ventes${item.payload.fiable ? "" : ", écart non significatif"})`,
                      `Étiquette ${item.payload.etiquette_dpe}`,
                    ]}
                  />
                  <Bar dataKey="ecart_vs_marche_pct" radius={[4, 4, 4, 4]}>
                    {dpe.resultats.map((d) => (
                      <Cell key={d.etiquette_dpe} fill={DPE_COULEURS[d.etiquette_dpe]} fillOpacity={d.fiable ? 1 : 0.35} />
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

      {/* ---------- MÉTHODE ---------- */}
      <section className="pt-20 sm:pt-28">
        <TitreSection
          sur="Méthode"
          titre="Des chiffres qu'on peut vérifier"
          sousTitre="Pas de modèle opaque : des règles écrites, les mêmes pour chaque commune et chaque quartier."
        />
        <Reveal>
          <div className="glass overflow-hidden">
            <div className="flex items-center gap-1 border-b border-line px-3 py-2.5" role="tablist" aria-label="Méthode">
              {Object.keys(ONGLETS).map((o) => (
                <button
                  key={o}
                  role="tab"
                  id={`onglet-${o}`}
                  aria-controls="panneau-methode"
                  aria-selected={onglet === o}
                  onClick={() => setOnglet(o)}
                  className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm transition-colors ${
                    onglet === o ? "bg-white/[0.07] text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {o}
                </button>
              ))}
            </div>
            <pre id="panneau-methode" role="tabpanel" aria-labelledby={`onglet-${onglet}`} className="code overflow-x-auto px-5 py-5 sm:px-7">
              {ONGLETS[onglet].map((l, i) => (
                <div key={i} className="whitespace-pre">
                  <span className="mr-5 inline-block w-4 select-none text-right text-[#3a3936]">{i + 1}</span>
                  {l[0] === "c" ? (
                    <span className="c">{l[1]}</span>
                  ) : (
                    <>
                      <span className="k">{l[1]}</span>
                      {l[2]}
                      <span className="s">{l[3]}</span>
                      <span className="c">{l[4]}</span>
                    </>
                  )}
                </div>
              ))}
            </pre>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
