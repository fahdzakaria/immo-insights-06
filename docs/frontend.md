# Frontend — Next.js, React Three Fiber, MapLibre

Dev : `npm run dev` dans `frontend/` (http://localhost:3000) — Docker :
service `frontend` du compose (image standalone multi-étapes).

> ⚠️ **Ne jamais lancer `npm run build` pendant que `npm run dev` tourne** :
> les deux partagent `.next/` et le build corrompt le serveur de dev
> (erreur `ENOENT _document.js`). Remède : stopper le dev, `rm -rf .next`,
> relancer.

## Les 7 vues

| Route | Vue | Ingrédients |
| --- | --- | --- |
| `/` | Marché (landing) | **Scène 3D R3F** : une barre par commune (position = GPS réel, hauteur = prix/m²), parallaxe souris ; KPIs à compteurs animés ; impact DPE |
| `/carte` | Carte | Choroplèthe MapLibre (polygones GeoJSON des 163 communes), 4 métriques commutables, tooltip au survol |
| `/tendances` | Tendances | Séries trimestrielles Recharts (prix + volumes), zoom par commune |
| `/comparateur` | Comparateur | Jusqu'à 3 communes côte à côte + radar des 6 composantes du score |
| `/rendement` | Rendement | Nuage prix/rendement (taille = fiabilité) + classement filtrable |
| `/estimateur` | Estimateur | Formulaire → estimation animée avec fourchette et méthode affichée |
| `/opportunites` | Opportunités | Cartes classées : anneau de score SVG animé + barres par composante |

## Design — « Terminal éditorial » (Bloomberg × presse)

Charbon chaud `#0c0c0a`, encre claire `#e8e4d6`, hairlines sombres, ombres
offset dures — zéro verre, zéro dégradé décoratif. **Un accent : l'ambre
terminal `#ffb020`** ; vert `#45d08c` / corail `#ff6b57` de cotation pour
les variations. Typo : **Fraunces** (titres serif, italique ambre pour
l'emphase), **Instrument Sans** (corps), **IBM Plex Mono** (chiffres
tabulaires, micro-labels uppercase, axes — utilitaire `.label-mono`).

Dynamisme : **bandeau ticker** défilant avec les cotations réelles des
communes (▲/▼, pause au survol, désactivé en `prefers-reduced-motion`),
pastille « live » pulsante, compteurs animés, reveals au scroll, anneaux de
score SVG. La scène 3D : barres braise→ambre sur plateau noir, entrée en
vague ouest→est, dérive de caméra + parallaxe, **survol par raycasting
manuel** — la barre visée passe corail et affiche commune + prix (étiquette
d'arpenteur suivant le curseur).

## Performance (la 3D ne pénalise jamais les données)

- **La 3D est chargée dynamiquement** (`next/dynamic`, `ssr: false`) et ne
  pèse que sur la landing ; `/carte` charge MapLibre seul (First Load JS :
  149-256 kB par route).
- **InstancedMesh** : les ~160 barres = 1 draw call ; `dpr` plafonné à 1.6.
- **Aucune donnée brute côté client** : chaque vue interroge les endpoints
  pré-agrégés (max 500 lignes), le filtrage est fait par l'API (WHERE +
  cache). La recoloration de la carte = `setData` sur la source GeoJSON,
  sans rechargement.
- Pages statiques pré-rendues par Next, données hydratées côté client.

## Accessibilité & responsive

Navigation clavier standard, contrastes AA sur le texte courant,
`aria-label` sur la scène 3D, layouts en grille qui passent en 1 colonne
sous `lg`, nav horizontale scrollable sur mobile (vérifié en 375 px).
