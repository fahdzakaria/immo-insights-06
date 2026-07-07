"use client";

/** Vue Carte : choroplèthe interactive, métrique et type de bien commutables. */

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { Metrique, ValeurCommune } from "@/components/CarteChoroplethe";
import { ToggleTypeBien } from "@/components/filtres";
import { Chargement, Erreur, TitreSection } from "@/components/ui";
import type { CommunePrix, Opportunite, Rendement, TypeBien } from "@/lib/api";
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

export default function PageCarte() {
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [metrique, setMetrique] = useState<Metrique>("prix_m2");

  const { data: prix, erreur } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: typeBien, limit: 500,
  });
  const { data: rendements } = useApi<{ resultats: Rendement[] }>("/api/v1/rendement", {
    departement: "06", type_bien: typeBien, limit: 500,
  });
  const { data: scores } = useApi<{ resultats: Opportunite[] }>("/api/v1/opportunites", {
    departement: "06", type_bien: typeBien, limit: 200,
  });

  const valeurs: ValeurCommune[] = useMemo(() => {
    if (!prix) return [];
    const rParCode = new Map(rendements?.resultats.map((r) => [r.code_commune, r]) ?? []);
    const sParCode = new Map(scores?.resultats.map((s) => [s.code_commune, s]) ?? []);
    return prix.resultats.map((c) => ({
      code: c.code_commune,
      nom: c.nom_commune,
      nbVentes: c.nb_ventes_24m,
      valeur:
        metrique === "prix_m2" ? c.prix_m2_median
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
        sousTitre="Survole une commune pour le détail. Les filtres recalculent la carte instantanément — les données sont pré-agrégées côté serveur."
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
      {erreur && <Erreur message={erreur} />}
      <div className="glass h-[68vh] min-h-[460px] overflow-hidden p-1.5">
        <Carte valeurs={valeurs} metrique={metrique} />
      </div>
      <p className="label-mono mt-3">
        Couleurs par quantiles — les communes restées éteintes n'ont pas assez de ventes récentes
        (garde-fou : ≥ 5 ventes sur 24 mois).
      </p>
    </div>
  );
}
