"use client";

/**
 * Carte choroplèthe MapLibre : polygones des 163 communes (GeoJSON local)
 * colorés par la métrique choisie, joints aux marts par code INSEE.
 * Tooltip au survol, recoloration instantanée quand un filtre change
 * (setData sur la source — aucun rechargement de tuiles).
 *
 * Maille quartier : au-delà de ZOOM_QUARTIERS, les communes découpées en
 * quartiers IRIS (Nice, Cannes, Antibes…) s'effacent au profit de leurs
 * quartiers. Les contours (/geo/iris-06.geojson, ~170 Ko compressés) ne sont
 * téléchargés qu'à l'approche de ce zoom. Communes et quartiers partagent
 * LA MÊME échelle de couleurs : une teinte veut dire le même prix aux deux
 * niveaux.
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

export interface ValeurQuartier {
  code: string;
  codeCommune: string;
  valeur: number | null;
  nbVentes: number;
  /** Au moins 20 ventes sur 24 mois */
  fiable: boolean;
  /** Écart du prix du quartier à la médiane de sa commune, en % */
  ecartCommune: number | null;
  /** Médiane de la commune : repère affiché quand le quartier n'a pas de chiffre */
  prixCommune: number | null;
}

/** Zoom à partir duquel les quartiers remplacent les communes découpées. */
export const ZOOM_QUARTIERS = 10.6;

// Rampes « braise » : éteintes → incandescentes, un seul registre par métrique
const CONFIG: Record<Metrique, { label: string; palette: string[]; format: (v: number) => string }> = {
  // 7 teintes : avec les quartiers, la majorité des valeurs tombe entre 4 000 et
  // 6 000 €/m² ; 4 seuils seulement noyaient tout le centre de Nice dans l'ambre
  prix_m2: {
    label: "Prix médian €/m²",
    palette: ["#26241b", "#3f3922", "#5f5126", "#866b28", "#b08626", "#e09f22", "#ffc457"],
    format: (v) => euro(v) + "/m²",
  },
  evolution: { label: "Évolution 1 an", palette: ["#ff6b57", "#3a382c", "#45d08c"], format: (v) => pct(v) },
  rendement: { label: "Rendement brut", palette: ["#26241b", "#2c4a3a", "#379a68", "#45d08c"], format: (v) => pct(v, false) },
  score: { label: "Score invest.", palette: ["#26241b", "#5c4030", "#b05442", "#ff6b57"], format: (v) => `${v}/100` },
};

const ETEINT = "#1b1a14";
const OPACITE = 0.85;
const AUCUN = ["==", ["get", "code"], ""] as maplibregl.FilterSpecification;

function quantiles(vals: number[], n: number): number[] {
  const tri = [...vals].sort((a, b) => a - b);
  return Array.from({ length: n }, (_, i) => tri[Math.floor(((i + 1) / (n + 1)) * (tri.length - 1))]);
}

/** Les propriétés d'une feature survolée arrivent sérialisées : null → "null". */
const lu = (v: unknown): number | null => (v == null || v === "null" || v === "" ? null : Number(v));

const ligneVentes = (n: number | null) =>
  n ? `<div style="color:#8a8574;font-size:12px">${nombre(n)} vente${n > 1 ? "s" : ""} sur 24 mois</div>` : "";

export default function CarteChoroplethe({
  valeurs,
  metrique,
  quartiers,
  cible,
}: {
  valeurs: ValeurCommune[];
  metrique: Metrique;
  /** Valeurs par quartier ; null quand la métrique n'existe qu'à la commune. */
  quartiers?: ValeurQuartier[] | null;
  /** Recentre la carte (raccourcis « Nice », « Cannes »…) ; `cle` change à chaque clic. */
  cible?: { centre: [number, number]; zoom: number; cle: number } | null;
}) {
  const conteneur = useRef<HTMLDivElement>(null);
  const carte = useRef<MlMap | null>(null);
  const geojson = useRef<GeoJSON.FeatureCollection | null>(null);
  const geoQuartiers = useRef<GeoJSON.FeatureCollection | null>(null);
  const pret = useRef(false);
  // Dernières props, lisibles depuis les gestionnaires posés une seule fois
  const etat = useRef({ valeurs, metrique, quartiers });
  etat.current = { valeurs, metrique, quartiers };
  const appliquer = useRef<() => void>(() => {});

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
    const quartiersVisibles = () =>
      !!etat.current.quartiers && !!geoQuartiers.current && map.getZoom() >= ZOOM_QUARTIERS;

    /** Colore communes et quartiers avec une échelle commune. */
    appliquer.current = () => {
      if (!geojson.current) return;
      const { valeurs, metrique, quartiers } = etat.current;
      const conf = CONFIG[metrique];
      // Une commune ne s'efface au profit de ses quartiers que si leurs couches
      // existent vraiment : contours en 404 ou lents → la commune reste colorée
      const couchesQuartiers = !!geoQuartiers.current && !!map.getLayer("quartiers-fill");
      const decoupees = new Set(couchesQuartiers ? (quartiers ?? []).map((q) => q.codeCommune) : []);

      const parCode = new Map(valeurs.map((v) => [v.code, v]));
      for (const f of geojson.current.features) {
        const p = f.properties as Record<string, unknown>;
        const v = parCode.get(p.code as string);
        p.valeur = v?.valeur ?? null;
        p.nbVentes = v?.nbVentes ?? null;
        p.affichage = v?.valeur != null ? conf.format(v.valeur) : null;
        p.decoupee = decoupees.has(p.code as string);
      }
      (map.getSource("communes") as maplibregl.GeoJSONSource).setData(geojson.current);

      // Échelle : quantiles sur communes + quartiers, pour qu'une teinte ait le
      // même sens aux deux niveaux de zoom
      const nonNulles = [...valeurs, ...(quartiers ?? [])]
        .map((v) => v.valeur)
        .filter((v): v is number => v != null);
      let couleur: maplibregl.ExpressionSpecification | string = ETEINT;
      if (nonNulles.length) {
        // Seuils strictement croissants (exigé par "step")
        const seuils = [...new Set(quantiles(nonNulles, conf.palette.length - 1))];
        const rampe: (string | number)[] = [];
        seuils.forEach((s, i) => rampe.push(s, conf.palette[i + 1]));
        couleur = [
          "case",
          ["==", ["get", "valeur"], null],
          ETEINT,
          ["step", ["to-number", ["get", "valeur"]], conf.palette[0], ...rampe],
        ] as maplibregl.ExpressionSpecification;
      }
      map.setPaintProperty("communes-fill", "fill-color", couleur);
      // Au zoom quartier, une commune découpée ne garde que son contour
      map.setPaintProperty("communes-fill", "fill-opacity", [
        "step", ["zoom"], OPACITE,
        ZOOM_QUARTIERS, ["case", ["boolean", ["get", "decoupee"], false], 0, OPACITE],
      ] as maplibregl.ExpressionSpecification);

      if (!geoQuartiers.current || !map.getSource("quartiers")) return;
      const visible = quartiers ? "visible" : "none";
      for (const id of ["quartiers-fill", "quartiers-line", "quartiers-hover"]) {
        map.setLayoutProperty(id, "visibility", visible);
      }
      if (!quartiers) return;
      const parIris = new Map(quartiers.map((q) => [q.code, q]));
      for (const f of geoQuartiers.current.features) {
        const p = f.properties as Record<string, unknown>;
        const q = parIris.get(p.code as string);
        p.valeur = q?.valeur ?? null;
        p.nbVentes = q?.nbVentes ?? 0;
        p.affichage = q?.valeur != null ? conf.format(q.valeur) : null;
        p.fiable = q?.fiable ?? false;
        p.ecart = q?.ecartCommune ?? null;
        p.prixCommune = q?.prixCommune ?? null;
      }
      (map.getSource("quartiers") as maplibregl.GeoJSONSource).setData(geoQuartiers.current);
      map.setPaintProperty("quartiers-fill", "fill-color", couleur);
    };

    /** À l'approche du zoom quartier : télécharge les contours et pose les couches. */
    let chargement = false;
    const chargerQuartiers = async () => {
      // Avant `load`, ni le style ni la couche communes-line n'existent : le
      // gestionnaire `load` rappelle cette fonction une fois la carte prête
      if (!pret.current || chargement || geoQuartiers.current || map.getZoom() < ZOOM_QUARTIERS - 0.8) return;
      chargement = true;
      try {
        const res = await fetch("/geo/iris-06.geojson");
        if (!res.ok) throw new Error(String(res.status));
        const geo = (await res.json()) as GeoJSON.FeatureCollection;
        // Carte démontée (ou remplacée, StrictMode) pendant le téléchargement
        if (carte.current !== map) return;
        map.addSource("quartiers", { type: "geojson", data: geo });
        // Sous les contours de communes, pour que la limite communale reste lisible
        map.addLayer({
          id: "quartiers-fill", type: "fill", source: "quartiers", minzoom: ZOOM_QUARTIERS,
          paint: { "fill-color": ETEINT, "fill-opacity": OPACITE },
        }, "communes-line");
        map.addLayer({
          id: "quartiers-line", type: "line", source: "quartiers", minzoom: ZOOM_QUARTIERS,
          paint: { "line-color": "rgba(12,12,10,0.55)", "line-width": 0.6 },
        }, "communes-line");
        map.addLayer({
          id: "quartiers-hover", type: "line", source: "quartiers", minzoom: ZOOM_QUARTIERS,
          paint: { "line-color": "#ffb020", "line-width": 2 },
          filter: AUCUN,
        });

        map.on("mousemove", "quartiers-fill", (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
          const f = e.features?.[0];
          if (!f) return;
          map.getCanvas().style.cursor = "pointer";
          map.setFilter("quartiers-hover", ["==", ["get", "code"], f.properties!.code]);
          const p = f.properties as Record<string, string>;
          const valeur = lu(p.valeur);
          const nb = lu(p.nbVentes) ?? 0;
          const ecart = lu(p.ecart);
          const prixCommune = lu(p.prixCommune);
          const estPrix = etat.current.metrique === "prix_m2";
          // Une évolution peut manquer malgré ≥ 5 ventes sur 24 mois : il faut
          // aussi 5 ventes l'année N-1 (ou N-3) pour comparer
          const absence =
            !estPrix && nb >= 5
              ? "Évolution non calculable : trop peu de ventes l'année précédente"
              : "Trop peu de ventes pour un chiffre fiable";
          const repere =
            valeur != null && estPrix && ecart != null
              ? `<div style="color:#8a8574;font-size:12px">${pct(ecart)} par rapport à ${p.nom_commune}</div>`
              : valeur == null && estPrix && prixCommune != null
                ? `<div style="color:#8a8574;font-size:12px">${p.nom_commune} : ${euro(prixCommune)}/m²</div>`
                : "";
          popup
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font-weight:700">${p.nom}</div>
               <div style="color:#8a8574;font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:3px">Quartier · ${p.nom_commune}</div>
               <div style="color:#ffb020;font-weight:600;font-variant-numeric:tabular-nums">${valeur == null ? absence : p.affichage}</div>
               ${repere}
               ${ligneVentes(nb)}
               ${valeur != null && String(p.fiable) !== "true" ? `<div style="color:#ff6b57;font-size:12px">Fiabilité faible : moins de 20 ventes</div>` : ""}`,
            )
            .addTo(map);
        });
        map.on("mouseleave", "quartiers-fill", () => {
          map.getCanvas().style.cursor = "";
          map.setFilter("quartiers-hover", AUCUN);
          popup.remove();
        });
        // Marqué chargé seulement une fois source ET couches posées
        geoQuartiers.current = geo;
        appliquer.current();
      } catch {
        // Contours indisponibles : la carte reste à la maille commune ; on
        // nettoie un ajout partiel pour qu'un prochain zoom puisse réessayer
        for (const id of ["quartiers-hover", "quartiers-line", "quartiers-fill"]) {
          if (map.getLayer(id)) map.removeLayer(id);
        }
        if (map.getSource("quartiers")) map.removeSource("quartiers");
      } finally {
        chargement = false;
      }
    };

    map.on("load", async () => {
      const geo = (await (await fetch("/geo/communes-06.geojson")).json()) as GeoJSON.FeatureCollection;
      geojson.current = geo;
      map.addSource("communes", { type: "geojson", data: geo });
      map.addLayer({
        id: "communes-fill",
        type: "fill",
        source: "communes",
        paint: { "fill-color": ETEINT, "fill-opacity": OPACITE },
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
        filter: AUCUN,
      });

      map.on("mousemove", "communes-fill", (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as Record<string, string>;
        // Commune découpée, au zoom quartier : c'est le quartier qui répond
        if (quartiersVisibles() && String(p.decoupee) === "true") {
          map.setFilter("communes-hover", AUCUN);
          return;
        }
        map.getCanvas().style.cursor = "pointer";
        map.setFilter("communes-hover", ["==", ["get", "code"], p.code]);
        const brut = lu(p.valeur);
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-weight:700;margin-bottom:2px">${p.nom}</div>
             <div style="color:#ffb020;font-weight:600;font-variant-numeric:tabular-nums">${brut == null ? "Trop peu de ventes pour un chiffre fiable" : p.affichage}</div>
             ${ligneVentes(lu(p.nbVentes))}`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "communes-fill", () => {
        map.getCanvas().style.cursor = "";
        map.setFilter("communes-hover", AUCUN);
        popup.remove();
      });

      pret.current = true;
      appliquer.current();
      chargerQuartiers();
    });
    map.on("zoom", chargerQuartiers);

    return () => {
      map.remove();
      carte.current = null;
      geoQuartiers.current = null;
      pret.current = false;
    };
  }, []);

  // Recoloration à chaque changement de métrique / valeurs (instantané)
  useEffect(() => {
    if (pret.current) appliquer.current();
  }, [valeurs, metrique, quartiers]);

  // Raccourcis de la page : vol vers une commune
  useEffect(() => {
    if (cible && carte.current) carte.current.flyTo({ center: cible.centre, zoom: cible.zoom, duration: 1400 });
  }, [cible]);

  return <div ref={conteneur} className="h-full w-full rounded-2xl" />;
}
