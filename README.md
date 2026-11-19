# Wowland — 上元灯夜

One repository for the web preview, Blender-authored assets, and delivery evidence.

## Structure

```text
apps/
  web/                     Next.js + React + Three.js preview
    public/models/         Runtime GLB models
    scripts/shangyuan/     Browser capture and playtest scripts
    src/lib/shangyuan/     Scene, water, post FX, audio, data
packages/
  assets/
    blender/               Original Shangyuan Blender build scripts
    lantern/               Palace lantern asset and reports
    lantern-river/         Modular kit, LOD, lookdev, and postprocess scripts; reports
    pavilion/              Hex pavilion asset and reports
    shangyuan/             Source GLBs, layout, previews, validation logs
docs/                      Plans and validation screenshots
```

## Frontend workflow

The repository uses pnpm workspaces and Biome.

```powershell
pnpm install
pnpm dev          # http://127.0.0.1:3000
pnpm check        # TypeScript + Biome
pnpm build
pnpm verify       # check + build
```

Browser verification, with `pnpm dev` running in another terminal:

```powershell
pnpm verify:visual
pnpm verify:flow
pnpm verify:mobile
```

## Asset workflow

Blender 5.3 headless scripts live under `packages/assets/*/scripts`. The main
lookdev pipeline is:

```powershell
$blender = 'D:\Workspace\Apps\Scoop\shims\blender.exe'
$root = 'D:\Coding\wowland\packages\assets\lantern-river'

& $blender -b --python-exit-code 1 --python "$root\scripts\build_kit.py"
& $blender -b --python-exit-code 1 --python "$root\scripts\build_lods.py"
& $blender -b --python-exit-code 1 --python "$root\scripts\build_scene.py"
python "$root\scripts\postprocess_renders.py"
```

Generated `.blend`, GLB, LOD, and render files from the lantern, lantern-river, and
pavilion pipelines are build outputs. Run their scripts to recreate them. Runtime GLBs
for the web preview stay in `apps/web/public/models/shangyuan/`, with their source
copies in `packages/assets/shangyuan/`.

Details and Unity import notes are in `packages/assets/lantern-river/README.md`.
