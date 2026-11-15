"use client";

/** Petits composants UI partagés : reveal au scroll, compteur animé, titres, états. */

import { motion, useInView, useMotionValue, useSpring } from "framer-motion";
import { useEffect, useRef } from "react";
import { SOURCE_DONNEES } from "@/lib/api";

/** Apparition douce au scroll (une seule fois). */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 22 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.55, delay, ease: [0.21, 0.65, 0.32, 1] }}
    >
      {children}
    </motion.div>
  );
}

/** Compteur animé : monte vers la valeur quand il entre dans le viewport. */
export function Compteur({
  valeur,
  suffixe = "",
  prefixe = "",
  decimales = 0,
  className = "",
}: {
  valeur: number;
  suffixe?: string;
  prefixe?: string;
  decimales?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { duration: 1400, bounce: 0 });

  useEffect(() => {
    if (inView) mv.set(valeur);
  }, [inView, valeur, mv]);

  useEffect(
    () =>
      spring.on("change", (v) => {
        if (ref.current)
          ref.current.textContent =
            prefixe +
            // Espace insécable classique : l'espace fine (U+202F) n'existe pas dans toutes les polices de titre
            v.toLocaleString("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: 0 }).replace(/\u202f/g, "\u00a0") +
            suffixe;
      }),
    [spring, prefixe, suffixe, decimales],
  );

  return (
    <span ref={ref} className={className}>
      {prefixe}0{suffixe}
    </span>
  );
}

export function TitreSection({ sur, titre, sousTitre }: { sur?: string; titre: string; sousTitre?: string }) {
  return (
    <div className="mb-12 sm:mb-16">
      {sur && (
        <div className="label-mono mb-5">{sur}</div>
      )}
      <h2 className="titre-degrade font-display text-3xl leading-[1.1] sm:text-[2.6rem]">{titre}</h2>
      {sousTitre && <p className="mt-4 max-w-2xl leading-relaxed text-muted">{sousTitre}</p>}
    </div>
  );
}

export function Chargement({ texte = "Chargement des données…" }: { texte?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      <span className="label-mono">{texte}</span>
    </div>
  );
}

/**
 * Message d'erreur. `technique` (défaut) = échec de chargement des données :
 * on ajoute un conseil adapté à la source. `technique={false}` = message
 * métier (ex. « pas assez de ventes »), affiché tel quel.
 */
export function Erreur({ message, technique = true }: { message: string; technique?: boolean }) {
  const conseil =
    SOURCE_DONNEES === "api" ? "vérifie que l’API tourne (docker compose up)" : "recharge la page";
  return (
    <div className="glass my-8 !border-bad/40 px-5 py-4 text-sm text-bad">
      ⚠ {message}{technique && ` — ${conseil}.`}
    </div>
  );
}
