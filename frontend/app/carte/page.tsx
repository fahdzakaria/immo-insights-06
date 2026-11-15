"use client";

/** Vue Carte : choroplèthe interactive, métrique et type de bien commutables. */

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { Metrique, ValeurCommune, ValeurQuartier } from "@/components/CarteChoroplethe";
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

export default function PageCarte() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [metrique, setMetrique] = useState<Metrique>("prix_m2");
  const [cible, setCible] = useState<{ centre: [number, number]; zoom: number; cle: number } | null>(null);

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
    <div className="pt-8">
      <TitreSection
        sur="Carte interactive"
        titre="Chaque commune, colorée par la donnée"
        sousTitre="Survole une commune pour le détail, zoome sur une ville pour descendre au quartier. Les filtres recalculent la carte instantanément — les données sont pré-agrégées."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ToggleTypeBien valeur={typeBien} onChange={(t) => t && setTypeBien(t)} />
        <div className="inline-flex border border-ink">
          {METRIQUES.map((m, i) => (
            <button
              key={m.id}
              onClick={() => setMetrique(m.id)}
              className={`label-mono cursor-pointer px-4 py-2 transition-colors ${
                i > 0 ? "border-l border-ink" : ""
              } ${metrique === m.id ? "bg-accent !text-bg" : "hover:bg-ink/5"}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {raccourcis.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="label-mono">Par quartier →</span>
          {raccourcis.map((r) => (
            <button
              key={r.code}
              onClick={() => setCible({ centre: r.centre, zoom: ZOOM_VILLE, cle: Date.now() })}
              title={`${r.nb} quartiers`}
              className="label-mono cursor-pointer border-b border-accent/50 pb-0.5 !text-ink transition-colors hover:border-accent hover:!text-accent"
            >
              {r.nom}
            </button>
          ))}
          {!maillesQuartier && (
            <span className="label-mono !text-bad">
              {metrique === "rendement" ? "Rendement" : "Score"} : à la commune seulement
            </span>
          )}
        </div>
      )}
      {erreur && <Erreur message={erreur} />}
      <div className="glass h-[68vh] min-h-[460px] overflow-hidden p-1.5">
        <Carte valeurs={valeurs} metrique={metrique} quartiers={quartiers} cible={cible} />
      </div>
      <p className="label-mono mt-3">
        Couleurs par quantiles — les communes restées éteintes ont moins de {SEUIL_VENTES_AFFICHAGE} ventes
        sur 24 mois : trop peu pour un prix de marché, quelle que soit la métrique.
        {maillesQuartier
          ? " En zoomant, les villes découpées par l'INSEE passent au quartier (IRIS), même échelle de couleurs ; un quartier éteint a moins de 5 ventes sur 24 mois (pour l'évolution : moins de 5 ventes sur l'une des deux années comparées)."
          : " Pas de loyers par quartier : rendement et score restent à la commune, même en zoomant."}
        {(metrique === "rendement" || metrique === "score") &&
          " Rendement et score : seules les communes au loyer mesuré localement (≥ 20 ventes) sont colorées."}
      </p>
    </div>
  );
}
