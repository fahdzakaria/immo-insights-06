"use client";

/** Vue Estimateur : formulaire → estimation transparente avec fourchette animée. */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { ChampRecherche, Curseur } from "@/components/filtres";
import { Compteur, Erreur, TitreSection } from "@/components/ui";
import type { CommunePrix, Estimation, TypeBien } from "@/lib/api";
import { apiGet } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { euro, nombre } from "@/lib/format";
import { DPE_COULEURS } from "@/lib/format";

export default function PageEstimateur() {
  const [recherche, setRecherche] = useState("");
  const [typeBien, setTypeBien] = useState<TypeBien>("appartement");
  const [surface, setSurface] = useState(60);
  const [dpe, setDpe] = useState<string | null>(null);
  const [resultat, setResultat] = useState<Estimation | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  const { data: communes } = useApi<{ resultats: CommunePrix[] }>("/api/v1/communes", {
    departement: "06", type_bien: "appartement", limit: 500,
  });
  const commune = communes?.resultats.find(
    (c) => c.nom_commune.toLowerCase() === recherche.toLowerCase(),
  );

  async function estimer() {
    if (!commune) return;
    setEnCours(true);
    setErreur(null);
    try {
      setResultat(await apiGet<Estimation>("/api/v1/estimation", {
        code_commune: commune.code_commune,
        type_bien: typeBien,
        surface,
        etiquette_dpe: dpe,
      }));
    } catch (e) {
      setResultat(null);
      setErreur("Pas assez de ventes récentes dans cette commune pour ce type de bien.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="pt-8">
      <TitreSection
        sur="Estimateur"
        titre="Combien vaut ce bien ?"
        sousTitre="Méthode 100 % transparente : médiane locale des ventes réelles sur 24 mois, ajustée de la décote DPE observée — pas de boîte noire."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        {/* -------- Formulaire -------- */}
        <div className="glass flex flex-col gap-6 px-6 py-7">
          <div>
            <label className="mb-1.5 block text-sm text-muted">Commune</label>
            <ChampRecherche
              valeur={recherche}
              onChange={setRecherche}
              liste={communes?.resultats.map((c) => c.nom_commune) ?? []}
              listeId="communes-estimateur"
              placeholder="Nice, Antibes, Grasse…"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm text-muted">Type de bien</label>
            <div className="flex gap-2">
              {(["appartement", "maison"] as TypeBien[]).map((t, i) => (
                <button key={t} onClick={() => setTypeBien(t)}
                        className={`label-mono cursor-pointer border border-ink px-4 py-2 transition-colors ${
                          typeBien === t ? "bg-ink !text-bg" : "hover:bg-ink/5"} ${i > 0 ? "-ml-px" : ""}`}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <Curseur label="Surface habitable" valeur={surface} onChange={setSurface}
                   min={10} max={250} format={(v) => `${v} m²`} />
          <div>
            <label className="mb-1.5 block text-sm text-muted">Étiquette DPE (optionnel)</label>
            <div className="flex flex-wrap gap-1.5">
              {["A", "B", "C", "D", "E", "F", "G"].map((e) => (
                <button key={e} onClick={() => setDpe(dpe === e ? null : e)}
                        className="h-9 w-9 cursor-pointer border font-bold transition-all"
                        style={{
                          background: dpe === e ? DPE_COULEURS[e] : "transparent",
                          color: dpe === e ? "#0c0c0a" : DPE_COULEURS[e],
                          borderColor: dpe === e ? "#e8e4d6" : DPE_COULEURS[e],
                          boxShadow: dpe === e ? "3px 3px 0 rgba(0,0,0,0.5)" : "none",
                        }}>
                  {e}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={estimer}
            disabled={!commune || enCours}
            className="label-mono mt-2 cursor-pointer border border-accent bg-accent px-6 py-3.5 !text-bg transition-colors enabled:hover:bg-[#ffc44d] disabled:opacity-40"
          >
            {enCours ? "Calcul…" : "Estimer ce bien →"}
          </button>
          {!commune && recherche && (
            <p className="text-sm text-warn">Choisis une commune dans la liste déroulante.</p>
          )}
        </div>

        {/* -------- Résultat -------- */}
        <div className="relative">
          <AnimatePresence mode="wait">
            {resultat ? (
              <motion.div
                key={JSON.stringify(resultat)}
                initial={{ opacity: 0, y: 20, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="glass flex h-full flex-col justify-center gap-5 px-6 py-8"
              >
                <div className="text-sm text-muted">
                  {resultat.type_bien} · {resultat.surface} m² · {resultat.nom_commune}
                  {resultat.etiquette_dpe && ` · DPE ${resultat.etiquette_dpe}`}
                </div>
                <div className="tabular font-display text-5xl font-black text-accent">
                  <Compteur valeur={resultat.prix_estime} suffixe=" €" />
                </div>

                {/* Fourchette */}
                <div>
                  <div className="mb-1.5 flex justify-between text-sm text-muted">
                    <span>{euro(resultat.fourchette_basse)}</span>
                    <span>{euro(resultat.fourchette_haute)}</span>
                  </div>
                  <div className="relative h-2 bg-ink/10">
                    <motion.div
                      className="absolute inset-y-0 bg-accent/25"
                      initial={{ width: 0 }}
                      animate={{ width: "100%" }}
                      transition={{ duration: 0.8, delay: 0.2 }}
                    />
                    <div
                      className="absolute top-1/2 h-4 w-4 -translate-y-1/2 border-2 border-panel bg-accent"
                      style={{
                        left: `${((resultat.prix_estime - resultat.fourchette_basse) /
                          (resultat.fourchette_haute - resultat.fourchette_basse)) * 100}%`,
                      }}
                    />
                  </div>
                  <div className="label-mono mt-2 text-center">fourchette = quartiles des ventes locales</div>
                </div>

                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div className="glass px-4 py-3">
                    <dt className="text-muted">Référence locale</dt>
                    <dd className="font-semibold">{euro(resultat.prix_m2_reference)}/m²</dd>
                  </div>
                  <div className="glass px-4 py-3">
                    <dt className="text-muted">Ajustement DPE</dt>
                    <dd className={`font-semibold ${resultat.ajustement_dpe_pct < 0 ? "text-bad" : "text-good"}`}>
                      {resultat.ajustement_dpe_pct > 0 ? "+" : ""}{resultat.ajustement_dpe_pct} %
                    </dd>
                  </div>
                </dl>
                <p className="text-xs text-muted">
                  Fiabilité : {nombre(resultat.fiabilite.nb_ventes_24m)} ventes comparables sur 24 mois.
                  Estimation indicative issue de données publiques, pas une expertise.
                </p>
              </motion.div>
            ) : (
              <motion.div key="vide" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          className="glass flex h-full min-h-[320px] items-center justify-center px-6 text-center text-muted">
                {erreur ? <Erreur message={erreur} /> : "Renseigne le bien à gauche, l'estimation apparaît ici."}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
