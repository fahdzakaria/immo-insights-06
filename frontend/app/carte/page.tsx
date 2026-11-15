"use client";

/** Vue Carte : choroplèthe interactive plein cadre, réglages dans un panneau
 *  façon « studio » (bien, mesure, villes, échelle). */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Echelle, Metrique, ValeurCommune, ValeurQuartier } from "@/components/CarteChoroplethe";
import { ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, TitreSection } from "@/components/ui";
import type { CommunePrix, Opportunite, QuartierPrix, Rendement, TypeBien } from "@/lib/api";
import { SEUIL_VENTES_AFFICHAGE } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const Carte = dynamic(() => import("@/components/CarteChoroplethe"), {
  ssr: false,
  loading: () => <Chargement texte="Initialisation de la carte…" />,
});

const METRIQUES: { id: Metrique; label: string }[] = [
  { id: "prix_m2", label: "Prix €/m²" },
  { id: "evolution", label: "Évolution 1 an" },
  { id: "rendement", label: "Rendement" },
  { id: "score", label: "Score invest." },
];

// Métriques disponibles au quartier : il n'existe pas de loyers par quartier,
// donc ni rendement ni score à cette maille
const METRIQUES_QUARTIER: Metrique[] = ["prix_m2", "evolution"];
const NB_RACCOURCIS = 6;
const ZOOM_VILLE = 11.7;

/** Section repliable du panneau studio. */
function Section({ titre, valeur, children }: { titre: string; valeur?: string; children: React.ReactNode }) {
  return (
    <details open className="group border-t border-line first:border-t-0">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="label-mono flex items-center gap-2">
          <span className="inline-block transition-transform group-open:rotate-90">›</span>
          {titre}
        </span>
        {valeur && <span className="text-xs text-ink">{valeur}</span>}
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}

export default function PageCarte() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [metrique, setMetrique] = useState<Metrique>("prix_m2");
  const [cible, setCible] = useState<{ centre: [number, number]; zoom: number; cle: number } | null>(null);
  const [echelle, setEchelle] = useState<Echelle | null>(null);
  const [panneauOuvert, setPanneauOuvert] = useState(true);
  const [monte, setMonte] = useState(false);
  // Sur téléphone le panneau couvrirait toute la carte : replié au départ
  // (masqué en CSS jusqu'au montage pour éviter qu'il s'affiche un instant)
  useEffect(() => {
    if (window.matchMedia("(max-width: 639px)").matches) setPanneauOuvert(false);
    setMonte(true);
  }, []);
  const recevoirEchelle = useCallback((e: Echelle | null) => setEchelle(e), []);

  const { data: prix, erreur } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: typeBien, limit: 500,
  });
  // Rendement et score : seulement les communes au loyer mesuré localement
  // (un loyer extrapolé donne des rendements irréalistes, cf. vue Rendement)
  const { data: rendements } = useApi<{ resultats: Rendement[] }>("/api/v1/rendement", {
    departement: "06", type_bien: typeBien, loyer_fiable: true, limit: 500,
  });
  const { data: scores } = useApi<{ resultats: Opportunite[] }>("/api/v1/opportunites", {
    departement: "06", type_bien: typeBien, loyer_fiable: true, limit: 200,
  });

  const { data: prixQuartiers } = useApi<{ resultats: QuartierPrix[] }>("/api/v1/quartiers", {
    departement: "06", type_bien: typeBien, limit: 2000,
  });

  const maillesQuartier = METRIQUES_QUARTIER.includes(metrique);
  const quartiers: ValeurQuartier[] | null = useMemo(() => {
    if (!prixQuartiers || !maillesQuartier) return null;
    return prixQuartiers.resultats.map((q) => ({
      code: q.code_iris,
      codeCommune: q.code_commune,
      nbVentes: q.nb_ventes_24m,
      fiable: q.fiable,
      ecartCommune: q.ecart_commune_pct,
      prixCommune: q.prix_m2_median_commune,
      // Sous 5 ventes le mart ne publie aucun chiffre : rien à masquer ici
      valeur: metrique === "prix_m2" ? q.prix_m2_median : q.evolution_1an_pct,
    }));
  }, [prixQuartiers, metrique, maillesQuartier]);

  // Raccourcis : les communes qui comptent le plus de quartiers
  const raccourcis = useMemo(() => {
    if (!prix || !prixQuartiers) return [];
    const nb = new Map<string, number>();
    for (const q of prixQuartiers.resultats) nb.set(q.code_commune, (nb.get(q.code_commune) ?? 0) + 1);
    return [...nb]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])) // ex æquo : ordre stable d'un type de bien à l'autre
      .slice(0, NB_RACCOURCIS)
      .flatMap(([code, n]) => {
        const c = prix.resultats.find((x) => x.code_commune === code);
        return c && c.latitude != null && c.longitude != null
          ? [{ code, nom: c.nom_commune, nb: n, centre: [c.longitude, c.latitude] as [number, number] }]
          : [];
      });
  }, [prix, prixQuartiers]);

  const valeurs: ValeurCommune[] = useMemo(() => {
    if (!prix) return [];
    const rParCode = new Map(rendements?.resultats.map((r) => [r.code_commune, r]) ?? []);
    const sParCode = new Map(scores?.resultats.map((s) => [s.code_commune, s]) ?? []);
    return prix.resultats.map((c) => ({
      code: c.code_commune,
      nom: c.nom_commune,
      nbVentes: c.nb_ventes_24m,
      valeur:
        // Garde-fou commun à toutes les métriques : pas de couleur sous 5 ventes
        // (une « médiane » sur 1 ou 2 ventes n'est pas un prix de marché)
        (c.nb_ventes_24m ?? 0) < SEUIL_VENTES_AFFICHAGE ? null
        : metrique === "prix_m2" ? c.prix_m2_median
        : metrique === "evolution" ? c.evolution_1an_pct
        : metrique === "rendement" ? rParCode.get(c.code_commune)?.rendement_brut_pct ?? null
        : sParCode.get(c.code_commune)?.score_investissement ?? null,
    }));
  }, [prix, rendements, scores, metrique]);

  return (
    <div className="pt-16 sm:pt-24">
      <TitreSection
        sur="Carte interactive"
        titre="Chaque commune, chaque quartier"
        sousTitre="Survolez une commune pour le détail, zoomez sur une ville pour descendre au quartier. Les réglages recalculent la carte instantanément : les données sont pré-agrégées."
      />
      {erreur && <Erreur message={erreur} />}

      <div className="glass relative h-[78vh] min-h-[560px] overflow-hidden !rounded-[20px] p-1.5">
        <div className="h-full overflow-hidden rounded-[14px]">
          <Carte valeurs={valeurs} metrique={metrique} quartiers={quartiers} cible={cible} onEchelle={recevoirEchelle} />
        </div>

        {/* Panneau « studio » */}
        <aside className={`absolute left-3 top-3 z-10 ${panneauOuvert ? "w-[min(290px,calc(100%-24px))]" : "w-auto"} overflow-hidden rounded-[14px] border border-line2 bg-[#0a0a0a]/95 shadow-[0_16px_40px_rgba(0,0,0,.6)]`}>
          <button
            onClick={() => setPanneauOuvert((o) => !o)}
            aria-expanded={panneauOuvert}
            className={`flex w-full cursor-pointer items-center justify-between gap-4 px-4 py-3 ${panneauOuvert ? "border-b border-line" : ""}`}
          >
            <span className="label-mono flex items-center gap-2 !text-ink">
              Studio · carte
            </span>
            <span className="text-xs text-muted">{panneauOuvert ? "Replier" : "Réglages"}</span>
          </button>
          {panneauOuvert && (
            <div className={`max-h-[calc(78vh-90px)] overflow-y-auto ${monte ? "" : "max-sm:hidden"}`}>
              <Section titre="Bien" valeur={typeBien === "appartement" ? "Appartements" : "Maisons"}>
                <ToggleTypeBien valeur={typeBien} onChange={(t) => t && setTypeBien(t)} />
              </Section>
              <Section titre="Mesure" valeur={METRIQUES.find((m) => m.id === metrique)?.label}>
                <div className="flex flex-col gap-0.5">
                  {METRIQUES.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setMetrique(m.id)}
                      aria-pressed={metrique === m.id}
                      className={`flex cursor-pointer items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors ${
                        metrique === m.id ? "bg-white/[0.07] text-ink" : "text-muted hover:text-ink"
                      }`}
                    >
                      {m.label}
                      <span className="label-mono">{METRIQUES_QUARTIER.includes(m.id) ? "quartier" : "commune"}</span>
                    </button>
                  ))}
                </div>
              </Section>
              {raccourcis.length > 0 && (
                <Section titre="Villes" valeur={`${raccourcis.length} raccourcis`}>
                  <div className="flex flex-wrap gap-1.5">
                    {raccourcis.map((r) => (
                      <button
                        key={r.code}
                        onClick={() => setCible({ centre: r.centre, zoom: ZOOM_VILLE, cle: Date.now() })}
                        title={`${r.nb} quartiers`}
                        className="btn btn-sm btn-sombre cursor-pointer"
                      >
                        {r.nom}
                      </button>
                    ))}
                  </div>
                  {!maillesQuartier && (
                    <p className="legende mt-3 !text-bad">
                      {metrique === "rendement" ? "Rendement" : "Score"} : à la commune seulement.
                    </p>
                  )}
                </Section>
              )}
              <Section titre="Échelle" valeur="quantiles">
                {echelle ? (
                  <>
                    <div className="flex h-2 overflow-hidden rounded-full">
                      {/* seuils dédoublonnés : seules les teintes réellement utilisées */}
                      {echelle.palette.slice(0, echelle.seuils.length + 1).map((c) => (
                        <span key={c} className="flex-1" style={{ background: c }} />
                      ))}
                    </div>
                    <div className="legende mt-1.5 flex justify-between tabular">
                      <span>&lt; {echelle.format(echelle.seuils[0])}</span>
                      <span>≥ {echelle.format(echelle.seuils[echelle.seuils.length - 1])}</span>
                    </div>
                  </>
                ) : (
                  <p className="legende">Pas de valeur à afficher.</p>
                )}
                <dl className="legende mt-3 grid grid-cols-[1fr_auto] gap-y-1">
                  <dt>Seuil d’affichage</dt>
                  <dd className="text-ink">{SEUIL_VENTES_AFFICHAGE} ventes</dd>
                  <dt>Fenêtre</dt>
                  <dd className="text-ink">24 mois</dd>
                  <dt className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#141414] ring-1 ring-line2" /> Éteint
                  </dt>
                  <dd className="text-ink">trop peu de ventes</dd>
                </dl>
              </Section>
            </div>
          )}
        </aside>
      </div>

      <p className="legende mt-6 max-w-4xl">
        Couleurs par quantiles. Une zone éteinte a moins de {SEUIL_VENTES_AFFICHAGE} ventes sur 24 mois : trop peu
        pour un prix de marché, quelle que soit la mesure.
        {maillesQuartier
          ? " En zoomant, les villes découpées par l'INSEE passent au quartier (IRIS), avec la même échelle de couleurs ; pour l'évolution, il faut aussi 5 ventes sur chacune des deux années comparées."
          : " Pas de loyers par quartier : rendement et score restent à la commune, même en zoomant."}
        {(metrique === "rendement" || metrique === "score") &&
          " Rendement et score : seules les communes au loyer mesuré localement (≥ 20 ventes) sont colorées."}
      </p>
    </div>
  );
}
