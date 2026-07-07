"use client";

/** Petits composants UI partagés : reveal au scroll, compteur animé, titres, états. */

import { motion, useInView, useMotionValue, useSpring } from "framer-motion";
import { useEffect, useRef } from "react";

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
            prefixe + v.toLocaleString("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: 0 }) + suffixe;
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
    <div className="mb-8 border-t-2 border-ink pt-4">
      {sur && <div className="label-mono mb-3 !text-accent">{sur}</div>}
      <h2 className="font-display text-3xl font-black tracking-tight sm:text-4xl">{titre}</h2>
      {sousTitre && <p className="mt-3 max-w-2xl leading-relaxed text-muted">{sousTitre}</p>}
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

export function Erreur({ message }: { message: string }) {
  return (
    <div className="glass border-bad/40 my-8 px-5 py-4 text-sm text-bad">
      ⚠ {message} — vérifie que l’API tourne (docker compose up).
    </div>
  );
}
