# 上元灯夜 / Lantern River Night — v3c Delivery

This folder contains the refined Blender kit, the night lookdev scene, LODs,
validation evidence, and graded stills for the lantern-river vertical slice.

## What shipped

| Layer | Path | Result |
|---|---|---|
| Modular kit | `exports/kit/*.fbx`, `*.glb` | 10 unique meshes, 68,460 tris total |
| LOD kit | `exports/kit/lod/` | LOD1 50 %, LOD2 22 %, all topology-clean |
| Lookdev scene | `exports/SM_Scene_LanternRiver_Night.blend` | 889 mesh objects, 686,850 tris, 52 lights, 5 cameras |
| Final stills | `renders/01_hero.png` … `05_boat.png` | 1920×1080 graded renders |
| Contact sheet | `renders/contact_sheet.png` | five-shot review board |
| Evidence | `reports/*.json` | kit, LOD, scene, and validation reports |
| Build scripts | `scripts/` | reproducible kit → LOD → scene → postprocess pipeline |

Kit piece triangle counts: bridge 6,756; tower 19,412; shophouse A 10,096,
B 12,616, C 10,416; pleasure boat 6,680; lantern string 1,624; hung lantern 292;
sky lantern 220; stall 348. The kit uses 14 shared `MAT_LR_*` materials.

## Production workflow

1. `blender-director` set the stage gates and deliverable contract in
   `PRODUCTION_BRIEF.md`.
2. `environment-artist` and `blender-modeler` defined the modular kit,
   silhouettes, deep window casings, dougong brackets, tiled eaves, balustrades,
   and the curved-hull boat.
3. `materials` and `lookdev` set the shared PBR palette, emissive hierarchy,
   procedural bump, night exposure, and roof-value lift.
4. `lighting` and `camera-cinematography` placed warm practicals, moon fill,
   roof rake, boat side fill, and five review cameras.
5. `rendering` and `compositing` rendered EEVEE at 1920×1080 with AgX and bloom.
6. `qa-review` ran `validate_asset.py` on every kit piece and checked LOD
   boundary/non-manifold counts.
7. `three-best-practices` guided the separate web preview atmosphere and
   draw-call budget.

## Validation evidence

- `reports/validate_kit_v3.json`: **PASS** for all 10 kit pieces; zero n-gons,
  non-manifold edges, boundary edges, loose geometry, or out-of-range UV loops.
- `reports/lod_report.json`: all 16 LOD meshes have zero boundary and
  non-manifold edges.
- `reports/scene_report.json`: 5 shots rendered from the saved lookdev scene.
- Web preview: full flow verified in Chrome at 1440×900 and 390×844; gate →
  claim → three riddles → lantern selection → blessing → release → show.
  Headless run measured 48–50 fps, 149–341 draw calls by phase/view, 16 textures,
  and zero console errors after adding the favicon. `npm run typecheck` passed.

## Design references

The visual direction follows the Portals `lantern-river` tokens: cobalt/violet
sky, warm paper light, dark timber, grey stone, wet reflections, FogExp2-style
depth, and restrained bloom. The web preview also uses its glass panel, serif
type, letter spacing, safe-area insets, and 44 px touch-target conventions.

## Rebuild

Paths use the placeholder kit filename exactly as written in the repository.

```powershell
$blender = 'D:\Workspace\Apps\Scoop\shims\blender.exe'
$root = 'D:\Coding\wowland\assets\lantern-river'

& $blender -b --python-exit-code 1 --python "$root\scripts\build_kit.py"
& $blender -b --python-exit-code 1 --python "$root\scripts\build_lods.py"
& $blender -b "$root\exports\SM_Env_LanternRiver_Kit" --python-exit-code 1 `
  --python 'C:\Users\19411_4bs7lzt\.agents\skills\blender-mcp-workflow\scripts\validate_asset.py' `
  -- --args-file '<args.json>'
& $blender -b --python-exit-code 1 --python "$root\scripts\build_scene.py"
python "$root\scripts\postprocess_renders.py"
```

Use `LR_FAST=1` with `build_scene.py` for 960×540 / 32-sample preview renders and
`LR_SKIP_RENDER=1` to rebuild the `.blend` without rendering.

## Unity URP import notes

- Use the FBX files. Scale is 1 unit = 1 metre, pivots are at base centre, and
  kit facades face local −Y. Apply transforms on import.
- Map `MAT_LR_Paper_Glow` and `MAT_LR_Paper_Red` to URP/Lit with Emission, or to
  a lightweight unlit emissive shader for mobile. Keep bloom around 0.4–0.7 with
  a threshold near 1.0 so paper glows without flattening the night grade.
- Blender's procedural bump is node-based and does not travel in FBX. Recreate
  stone, plaster, wood, and roof detail with shared normal maps or shader graph
  noise in Unity if the mobile target allows it.
- Put LOD0, LOD1, and LOD2 in a `LODGroup`. A starting point is LOD0 from 0 m,
  LOD1 from 25 m, LOD2 from 60 m, and cull beyond 120 m; tune by screen size.
- Disable realtime shadows on the many point/area practicals. Keep one shadow
  directional moon and bake or fake the warm pools.
- The 686,850-triangle count belongs to the offline lookdev beauty scene. The
  shipped web preview uses a separate 270k-triangle budget with adaptive quality.

## Known limits

- No Unity project has been created or integrated; this folder is the art
  handoff.
- The lookdev scene exceeds the earlier 600k target, so the brief now records a
  700k beauty-scene cap and keeps the runtime budget separate.
- The web preview worktree carries pre-existing tracked deletions outside
  `src/` and `public/`; those files were left untouched during this pass.
