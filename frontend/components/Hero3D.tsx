"use client";

/**
 * Scène 3D « maquette d'architecte » : chaque barre est une vraie commune
 * (position GPS, hauteur = prix médian au m²), encre → bleu Klein.
 *
 * - InstancedMesh : ~160 barres = 1 draw call
 * - Entrée en VAGUE : les barres poussent d'ouest en est, easing back
 * - SURVOL : raycasting manuel dans la boucle de rendu (listener DOM natif
 *   → coordonnées normalisées → intersectObject sur les instances) ; la
 *   barre visée passe en terracotta et remonte (commune, prix) au parent
 * - Caméra : dérive lente + parallaxe souris amortie
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { CommunePrix } from "@/lib/api";
import { SEUIL_VENTES_AFFICHAGE } from "@/lib/api";

export interface SurvolCommune {
  nom: string;
  prix: number;
}

const TAILLE = 26;
const BRAISE_ETEINTE = new THREE.Color("#3d3a2c"); // communes bon marché
const AMBRE = new THREE.Color("#ffb020"); // communes chères
const CORAIL = new THREE.Color("#ff6b57"); // surlignage du survol

interface Barre {
  x: number;
  z: number;
  h: number;
  delai: number;
  couleur: THREE.Color;
  nom: string;
  prix: number;
}

function easeOutBack(t: number): number {
  const c1 = 1.2;
  return 1 + (c1 + 1) * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

function Barres({
  communes,
  onSurvol,
}: {
  communes: CommunePrix[];
  onSurvol: (s: SurvolCommune | null) => void;
}) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const temps = useRef(0);
  const survolId = useRef<number | null>(null);
  const pointeur = useRef(new THREE.Vector2(-10, -10)); // hors écran = pas de survol
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const { gl, camera } = useThree();

  const barres: Barre[] = useMemo(() => {
    // Pas de barre pour une commune à moins de 5 ventes : son « prix » serait
    // celui d'une ou deux ventes isolées (et fausserait l'échelle des hauteurs).
    const geo = communes.filter(
      (c) => c.latitude && c.longitude && c.prix_m2_median && (c.nb_ventes_24m ?? 0) >= SEUIL_VENTES_AFFICHAGE,
    );
    const lons = geo.map((c) => c.longitude!);
    const lats = geo.map((c) => c.latitude!);
    const pMax = Math.max(...geo.map((c) => c.prix_m2_median!));
    const [lo0, lo1] = [Math.min(...lons), Math.max(...lons)];
    const [la0, la1] = [Math.min(...lats), Math.max(...lats)];
    return geo.map((c) => {
      const t = c.prix_m2_median! / pMax;
      const x = ((c.longitude! - lo0) / (lo1 - lo0) - 0.5) * TAILLE;
      return {
        x,
        z: -((c.latitude! - la0) / (la1 - la0) - 0.5) * (TAILLE * 0.7),
        h: 0.35 + t * 7.5,
        delai: ((x + TAILLE / 2) / TAILLE) * 1.1, // la vague balaie d'ouest en est
        couleur: BRAISE_ETEINTE.clone().lerp(AMBRE, Math.pow(t, 0.8)),
        nom: c.nom_commune,
        prix: c.prix_m2_median!,
      };
    });
  }, [communes]);

  // Couleurs par instance : setColorAt crée mesh.instanceColor (indispensable
  // aussi au surlignage du survol).
  useEffect(() => {
    if (!mesh.current) return;
    barres.forEach((b, i) => mesh.current!.setColorAt(i, b.couleur));
    mesh.current.instanceColor!.needsUpdate = true;
  }, [barres]);

  // Suivi souris par listener DOM natif : fiable, indépendant du système
  // d'événements React/R3F.
  useEffect(() => {
    const el = gl.domElement;
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointeur.current.set(
        ((e.clientX - r.left) / r.width) * 2 - 1,
        -((e.clientY - r.top) / r.height) * 2 + 1,
      );
    };
    const onLeave = () => pointeur.current.set(-10, -10);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [gl]);

  useFrame((_, delta) => {
    if (!mesh.current) return;
    temps.current += delta;
    const m = new THREE.Matrix4();
    barres.forEach((b, i) => {
      const t = Math.min(1, Math.max(0, (temps.current - b.delai) / 0.9));
      const grandit = t === 0 ? 0.001 : easeOutBack(t);
      const focus = i === survolId.current ? 1.7 : 1;
      const h = Math.max(0.001, b.h * grandit);
      m.makeScale(focus, h, focus);
      m.setPosition(b.x, h / 2, b.z);
      mesh.current!.setMatrixAt(i, m);
    });
    mesh.current.instanceMatrix.needsUpdate = true;

    // Raycast manuel : quelle barre est sous le curseur ?
    let id: number | null = null;
    if (pointeur.current.x > -5) {
      raycaster.setFromCamera(pointeur.current, camera);
      const hits = raycaster.intersectObject(mesh.current, false);
      id = hits.length ? (hits[0].instanceId ?? null) : null;
    }
    if (id !== survolId.current && mesh.current.instanceColor) {
      // (instanceColor est garanti par l'effet d'initialisation ci-dessus)
      if (survolId.current !== null)
        mesh.current.setColorAt(survolId.current, barres[survolId.current].couleur);
      if (id !== null) mesh.current.setColorAt(id, CORAIL);
      mesh.current.instanceColor.needsUpdate = true;
      survolId.current = id;
      onSurvol(id === null ? null : { nom: barres[id].nom, prix: barres[id].prix });
      gl.domElement.style.cursor = id === null ? "" : "crosshair";
    }

    // Dérive lente + parallaxe souris amortie
    const px = pointeur.current.x > -5 ? pointeur.current.x : 0;
    const py = pointeur.current.x > -5 ? pointeur.current.y : 0;
    const derive = Math.sin(temps.current * 0.12) * 2.2;
    camera.position.x += (derive + px * 3 - camera.position.x) * 0.03;
    camera.position.y += (9.5 + py * 2 - camera.position.y) * 0.03;
    camera.lookAt(0, 1.4, 0);
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, barres.length]} key={barres.length}>
      <boxGeometry args={[0.24, 1, 0.24]} />
      <meshStandardMaterial color="#ffffff" toneMapped={false} roughness={0.55} metalness={0.05} />
    </instancedMesh>
  );
}

function Plateau() {
  return (
    <>
      <gridHelper args={[TAILLE * 1.7, 46, "#33301f", "#1a1913"]} position={[0, 0, 0]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} receiveShadow>
        <planeGeometry args={[130, 130]} />
        <meshStandardMaterial color="#0c0c0a" roughness={1} />
      </mesh>
    </>
  );
}

export default function Hero3D({
  communes,
  onSurvol,
}: {
  communes: CommunePrix[];
  onSurvol: (s: SurvolCommune | null) => void;
}) {
  return (
    <Canvas
      dpr={[1, 1.6]}
      shadows
      camera={{ position: [0, 9.5, 16.5], fov: 40 }}
      gl={{ antialias: true, alpha: true }}
      aria-label="Maquette 3D des prix immobiliers : une barre par commune, hauteur = prix au m². Survolez pour le détail."
    >
      <fog attach="fog" args={["#0c0c0a", 24, 48]} />
      <ambientLight intensity={0.55} />
      <directionalLight
        position={[10, 16, 8]}
        intensity={1.8}
        color="#fff2d9"
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      <directionalLight position={[-8, 6, -4]} intensity={0.5} color="#ffb020" />
      <Barres communes={communes} onSurvol={onSurvol} />
      <Plateau />
    </Canvas>
  );
}
