"use client";

/**
 * Carte choroplèthe MapLibre : polygones des 163 communes (GeoJSON local)
 * colorés par la métrique choisie, joints aux marts par code INSEE.
 * Tooltip au survol, recoloration instantanée quand un filtre change
 * (setData sur la source — aucun rechargement de tuiles).
 */

import maplibregl, { Map as MlMap, MapMouseEvent, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { euro, nombre, pct } from "@/lib/format";

export type Metrique = "prix_m2" | "evolution" | "rendement" | "score";

export interface ValeurCommune {
  code: string;
  nom: string;
  valeur: number | null;
  nbVentes: number | null;
}

// Rampes « braise » : éteintes → incandescentes, un seul registre par métrique
const CONFIG: Record<Metrique, { label: string; palette: string[]; format: (v: number) => string }> = {
  prix_m2: { label: "Prix médian €/m²", palette: ["#26241b", "#4d4426", "#8a6f28", "#c99424", "#ffb020"], format: (v) => euro(v) + "/m²" },
  evolution: { label: "Évolution 1 an", palette: ["#ff6b57", "#3a382c", "#45d08c"], format: (v) => pct(v) },
  rendement: { label: "Rendement brut", palette: ["#26241b", "#2c4a3a", "#379a68", "#45d08c"], format: (v) => pct(v, false) },
  score: { label: "Score invest.", palette: ["#26241b", "#5c4030", "#b05442", "#ff6b57"], format: (v) => `${v}/100` },
};

function quantiles(vals: number[], n: number): number[] {
  const tri = [...vals].sort((a, b) => a - b);
  return Array.from({ length: n }, (_, i) => tri[Math.floor(((i + 1) / (n + 1)) * (tri.length - 1))]);
}

export default function CarteChoroplethe({
  valeurs,
  metrique,
}: {
  valeurs: ValeurCommune[];
  metrique: Metrique;
}) {
  const conteneur = useRef<HTMLDivElement>(null);
  const carte = useRef<MlMap | null>(null);
  const geojson = useRef<GeoJSON.FeatureCollection | null>(null);
  const pret = useRef(false);

  // Initialisation unique de la carte
  useEffect(() => {
    if (!conteneur.current || carte.current) return;
    const map = new maplibregl.Map({
      container: conteneur.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [7.1, 43.85],
      zoom: 8.4,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    carte.current = map;

    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 });

    map.on("load", async () => {
      const geo = (await (await fetch("/geo/communes-06.geojson")).json()) as GeoJSON.FeatureCollection;
      geojson.current = geo;
      map.addSource("communes", { type: "geojson", data: geo });
      map.addLayer({
        id: "communes-fill",
        type: "fill",
        source: "communes",
        paint: { "fill-color": "#1b1a14", "fill-opacity": 0.85 },
      });
      map.addLayer({
        id: "communes-line",
        type: "line",
        source: "communes",
        paint: { "line-color": "rgba(232,228,214,0.22)", "line-width": 0.5 },
      });
      map.addLayer({
        id: "communes-hover",
        type: "line",
        source: "communes",
        paint: { "line-color": "#ffb020", "line-width": 2 },
        filter: ["==", ["get", "code"], ""],
      });

      map.on("mousemove", "communes-fill", (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = "pointer";
        map.setFilter("communes-hover", ["==", ["get", "code"], f.properties!.code]);
        const p = f.properties as Record<string, string>;
        const brut = p.valeur === "null" || p.valeur === undefined ? null : Number(p.valeur);
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-weight:700;margin-bottom:2px">${p.nom}</div>
             <div style="color:#ffb020;font-weight:600;font-variant-numeric:tabular-nums">${brut == null ? "Pas assez de ventes" : p.affichage}</div>
             ${p.nbVentes && p.nbVentes !== "null" ? `<div style="color:#8a8574;font-size:12px">${nombre(Number(p.nbVentes))} ventes sur 24 mois</div>` : ""}`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "communes-fill", () => {
        map.getCanvas().style.cursor = "";
        map.setFilter("communes-hover", ["==", ["get", "code"], ""]);
        popup.remove();
      });

      pret.current = true;
      map.fire("recolorer" as never);
    });

    return () => {
      map.remove();
      carte.current = null;
      pret.current = false;
    };
  }, []);

  // Recoloration à chaque changement de métrique / valeurs (instantané)
  useEffect(() => {
    const map = carte.current;
    const geo = geojson.current;
    const appliquer = () => {
      if (!map || !geojson.current) return;
      const conf = CONFIG[metrique];
      const parCode = new Map(valeurs.map((v) => [v.code, v]));
      for (const f of geojson.current.features) {
        const p = f.properties as Record<string, unknown>;
        const v = parCode.get(p.code as string);
        p.valeur = v?.valeur ?? null;
        p.nbVentes = v?.nbVentes ?? null;
        p.affichage = v?.valeur != null ? conf.format(v.valeur) : null;
      }
      (map.getSource("communes") as maplibregl.GeoJSONSource).setData(geojson.current);

      const nonNulles = valeurs.map((v) => v.valeur).filter((v): v is number => v != null);
      if (nonNulles.length) {
        const seuils = quantiles(nonNulles, conf.palette.length - 1);
        const rampe: (string | number)[] = [];
        seuils.forEach((s, i) => rampe.push(s, conf.palette[i + 1]));
        map.setPaintProperty("communes-fill", "fill-color", [
          "case",
          ["==", ["get", "valeur"], null],
          "#1b1a14",
          ["step", ["to-number", ["get", "valeur"]], conf.palette[0], ...rampe],
        ]);
      }
    };
    if (pret.current) appliquer();
    else map?.on("recolorer" as never, appliquer);
  }, [valeurs, metrique]);

  return <div ref={conteneur} className="h-full w-full rounded-2xl" />;
}
