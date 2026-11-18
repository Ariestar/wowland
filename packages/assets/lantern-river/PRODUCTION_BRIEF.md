# Production Brief — 上元灯夜 / Lantern River Night (v3 detail pass)

**Stage:** model + look development + lighting + delivery
**Date:** 2026-11-18
**Owner:** Technical art (Blender 5.3 headless) → Next.js / three.js preview

## 1. Intent

The first pushed scene proved the loop (walk, riddle, release, show). The current
models read as blockout: flat glowing panels, plain wall planes, roof slabs, and
foreground boats that silhouette as black boxes. This pass raises the asset to a
shippable vertical slice by adding real architectural detail where the camera
looks, and by giving every surface a designed material and light response.

The reference is the Portals «lantern-river» palette and the visual grammar of a
Jiangnan water town at night: deep cobalt sky with a violet horizon band, warm
paper light, dark timber, grey stone, wet reflections, layered silhouettes.

## 2. Deliverables

| Layer | Deliverable | Path |
|---|---|---|
| Modular kit | 3 shophouses, arch bridge, 5-tier lantern tower, market stall, lantern props | `assets/lantern-river/exports/kit/` |
| LODs | LOD1 50 %, LOD2 22 % per kit piece | `assets/lantern-river/exports/kit/lod/` |
| Lookdev scene | 5 graded 1920×1080 stills + contact sheet | `assets/lantern-river/renders/` |
| Web preview | Upgraded atmosphere, materials and hero geometry | `origin/shangyuan-lantern-night` worktree |
| Evidence | kit / LOD / scene / validation reports | `assets/lantern-river/reports/` |

## 3. Budgets

| Asset | LOD0 tris | LOD1 | LOD2 | Notes |
|---|---:|---:|---:|---|
| Shophouse A/B/C | ≤ 18 000 each | 50 % | 22 % | facade detail concentrated on river side |
| Lantern tower | ≤ 55 000 | 50 % | 22 % | hero landmark, 8-sided, 5 tiers |
| Arch bridge | ≤ 25 000 | 50 % | 22 % | 44 m span, stone + red rails |
| Market stall | ≤ 6 000 | 50 % | 22 % | reusable prop |
| Pleasure boat | ≤ 20 000 | — | — | one-off scene prop |
| Whole lookdev scene | ≤ 700 000 | — | — | beauty scene only; runtime web stays ≈270 000 |
| Materials | 14 shared kit materials | — | — | 2–12 slots per mesh; scene-only materials separate |
| Textures | 0 runtime for GLB | — | — | material colour + procedural bump in Blender |

Naming: `SM_Env_*`, `SM_Prop_*`; pivot base centre; front facade local −Y.
Scale: metres, applied transforms. UVs: 0–1 packed, no out-of-bounds.

## 4. Active workflow

1. `blender-director` — stage gates and run structure
2. `environment-artist` — modular architecture, silhouette, rhythm
3. `blender-modeler` — clean watertight shells, bevels, trim
4. `materials` + `lookdev` — PBR values, emissive hierarchy, value read
5. `lighting` + `camera-cinematography` — key/fill/rim, practical pools, lenses
6. `rendering` + `compositing` — 1920×1080 EEVEE, AgX, bloom, grade
7. `qa-review` — topology, UV, naming, budget, visual acceptance
8. `three-best-practices` — renderer budget, draw calls, bloom, texture cost

N/A with reason: rigging/animation (static environment); collision proxies
(web preview uses analytic blockers).

## 5. Stage gates

| # | Stage | Gate evidence | Status |
|---|---|---|---|
| 1 | inspect | kit + scene audit, current renders | PASS |
| 2 | brief | this document | PASS |
| 3 | model | `validate_asset.py` geometry checks on every kit piece | PASS |
| 4 | look_dev | UV + material checks, 4-up capture | PASS |
| 5 | light_camera | hero / bridge / tower / street / water framing | PASS |
| 6 | validate | `validate_asset.py` PASS, WARN only with reason | PASS |
| 7 | export | GLB + FBX written for every piece and LOD | PASS |
| 8 | verify | GLB headers, report counts, browser smoke | PASS |

## 6. Detail plan (what changes)

- **Windows:** recessed four-sided casing, projecting sill, paper inset, 4×3
  lattice, transom above; no more single glowing rectangle.
- **Facades:** corner posts, floor bands, sloped fabric awning with scalloped
  valance, perpendicular shop sign, eave bracket sets (dougong), eave tile caps,
  upturned corner tips.
- **Tower:** per-tier balcony and railing, bracket rings, recessed lattice bays
  on all eight faces, eave tile caps, corner bells, layered finial.
- **Bridge:** deck stone joints, arch keystone, balustrade panels, end steps.
- **Boat:** raised sheer, gunwale trim, cabin lattice, curved roof, deck rail,
  lantern posts; replaces the black foreground silhouettes.
- **Light:** keep one shadow-casting moon; warm practicals per facade; tower
  tier glow; water streaks. No shadow-buffer overflow.
- **Grade:** AgX, medium-high contrast, exposure 0.55, bloom threshold 1.3.

### v3c correction pass

- Boat cabin paper and lattice were embedded inside the solid wall, so their
  emission never reached the camera. They now sit outside the wall face, with a
  scene-only brighter paper material on the boat's object-level material slot.
- Boat lighting adds a camera-side fill; the chosen camera sees the roof, three
  lattice windows, the sheer line, and the water reflection together.
- Sky lanterns start farther from the hero camera and use a smaller scale range
  to remove large flat discs from the foreground; star emission was reduced.
- Roof materials were lifted in the lookdev scene so the tile courses survive
  the night grade.
- Blender CLI commands now use `--python-exit-code 1`; a Python traceback can no
  longer be reported as a successful build step.

## 7. Acceptance

- All geometry checks PASS; no non-manifold or boundary edges introduced.
- Kit and LOD budgets met; lookdev scene stays under 700 000 triangles.
- Hero still reads at 100 % zoom: tower silhouette, bridge arc, three layers of
  depth, warm/cool separation, no black voids.
- Web preview: gate → claim → riddle → choose lantern → release → show pass in
  Chrome at 1440×900 and 390×844; no console errors; draw calls under 250 in the
  main street view.
