"use client";

/**
 * Visuel texturé façon Pryzm, tiré de la donnée : le vrai contour d'une
 * commune ou d'un quartier, rempli d'une texture (trame de points, verre
 * cannelé ou pixels) dans la teinte de son prix. Rien de décoratif : la forme
 * et la couleur viennent des données.
 */

import { useEffect, useRef } from "react";
import { boite, type Geometrie, projection, tracer } from "@/lib/geo";

export type Texture = "trame" | "cannele" | "pixels";

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgba = (hex: string, k: number, a = 1) => {
  const [r, g, b] = rgb(hex).map((c) => Math.min(255, Math.round(c * k)));
  return `rgba(${r},${g},${b},${a})`;
};
const bruit = (x: number, y: number, s: number) => {
  const n = Math.sin(x * 127.1 + y * 311.7 + s * 74.7) * 43758.5453;
  return n - Math.floor(n);
};

function dessiner(cv: HTMLCanvasElement, g: Geometrie, couleur: string, texture: Texture, graine: number) {
  const w = cv.clientWidth;
  const h = cv.clientHeight;
  if (!w || !h) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = Math.round(w * dpr);
  cv.height = Math.round(h * dpr);
  const ctx = cv.getContext("2d")!;
  ctx.scale(dpr, dpr);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);

  const proj = projection(boite(g), w, h, 22);
  // Masque de couverture, échantillonné pour placer la texture
  const m = document.createElement("canvas");
  m.width = Math.ceil(w);
  m.height = Math.ceil(h);
  const mx = m.getContext("2d", { willReadFrequently: true })!;
  mx.fillStyle = "#fff";
  tracer(mx, g, proj);
  mx.fill("evenodd");
  const md = mx.getImageData(0, 0, m.width, m.height).data;
  const couv = (x: number, y: number) => {
    x = Math.round(x);
    y = Math.round(y);
    return x < 0 || y < 0 || x >= m.width || y >= m.height ? 0 : md[(y * m.width + x) * 4 + 3] / 255;
  };
  let plein = 0;
  for (let i = 3; i < md.length; i += 16) if (md[i] > 127) plein++;
  const fraction = plein / (md.length / 16);

  if (texture === "trame") {
    const pas = 7;
    for (let y = pas / 2; y < h; y += pas)
      for (let x = pas / 2; x < w; x += pas) {
        if (couv(x, y) < 0.5) continue;
        const lum = Math.max(0, Math.min(1, 0.55 + 0.45 * ((x / w) * 0.6 - (y / h) * 0.9) + (bruit(x, y, graine) - 0.5) * 0.18));
        ctx.fillStyle = rgba(couleur, 0.55 + 0.6 * lum);
        ctx.beginPath();
        ctx.arc(x, y, pas * 0.5 * (0.18 + 0.82 * lum), 0, Math.PI * 2);
        ctx.fill();
      }
  } else if (texture === "cannele") {
    const o = document.createElement("canvas");
    o.width = Math.ceil(w);
    o.height = Math.ceil(h);
    const ox = o.getContext("2d")!;
    const gr = ox.createLinearGradient(0, 0, w, h);
    gr.addColorStop(0, rgba(couleur, 1.15));
    gr.addColorStop(0.6, rgba(couleur, 0.7));
    gr.addColorStop(1, rgba(couleur, 0.28));
    ox.fillStyle = gr;
    tracer(ox, g, proj);
    ox.fill("evenodd");
    const bande = 10;
    for (let x = 0; x < w; x += bande) {
      for (let j = 0; j < bande; j++) {
        const f = j / bande;
        ctx.globalAlpha = 0.55 + 0.45 * Math.sin(f * Math.PI);
        const src = Math.max(0, Math.min(w - 1, x + j + (f - 0.5) * 14)) | 0;
        ctx.drawImage(o, src, 0, 1, h, x + j, 0, 1, h);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(0,0,0,.55)";
      ctx.fillRect(x, 0, 1, h);
    }
  } else {
    const pas = 8;
    for (let y = 0; y < h; y += pas)
      for (let x = 0; x < w; x += pas) {
        const c = (couv(x + 2, y + 2) + couv(x + 6, y + 2) + couv(x + 2, y + 6) + couv(x + 6, y + 6)) / 4;
        if (c < 0.4) continue;
        const n = bruit(x / pas, y / pas, graine);
        ctx.fillStyle = rgba(couleur, 0.35 + 0.9 * n, 0.5 + 0.5 * n);
        ctx.fillRect(x + 0.5, y + 0.5, pas - 1, pas - 1);
      }
  }

  // Contour réel ; plus marqué quand la forme est trop fine pour porter la texture
  tracer(ctx, g, proj);
  if (fraction < 0.08) {
    ctx.shadowColor = couleur;
    ctx.shadowBlur = 12;
    ctx.strokeStyle = rgba(couleur, 1.2);
    ctx.lineWidth = 1.6;
  } else {
    ctx.strokeStyle = "rgba(255,255,255,.2)";
    ctx.lineWidth = 0.75;
  }
  ctx.stroke();
}

export default function VisuelForme({
  geometrie,
  couleur,
  texture,
  graine = 1,
  className = "",
  label,
}: {
  geometrie: Geometrie;
  couleur: string;
  texture: Texture;
  graine?: number;
  className?: string;
  label: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const rendu = () => dessiner(cv, geometrie, couleur, texture, graine);
    rendu();
    const ro = new ResizeObserver(rendu);
    ro.observe(cv);
    return () => ro.disconnect();
  }, [geometrie, couleur, texture, graine]);
  return <canvas ref={ref} role="img" aria-label={label} className={`block h-full w-full ${className}`} />;
}
