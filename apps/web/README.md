# 上元灯夜（网页预览）

一个可以走进去的宋代水城上元灯会：领灯、猜一道谜、放河灯，看一场灯会。Next.js 16 + React 19 + three.js。

制作方案见仓库根目录的《桃源上元灯会_制作方案.md》，MVP 交互验收见 `docs/plans/2026-11-19-mvp-vertical-slice.md`，早期预览设计见 `docs/plans/2026-11-14-shangyuan-lantern-night.md`。

当前版本对应 PRD v1.0 的 MVP-A 主线规则（一摊一谜、统一资格、选灯祝词合并面板、
河灯 5 盏上限 / 10s 冷却 / 60s 回收）与 G0 狸奴占位原型（面具入口、扑筐、跃上矮棚、安全退出）。

## 运行

在仓库根目录使用 pnpm：

```bash
pnpm install
pnpm dev        # http://127.0.0.1:3000/
pnpm check      # TypeScript + Biome
pnpm build
```

浏览器验收脚本需要先启动 `pnpm dev`：

```bash
pnpm verify:visual
pnpm verify:flow
pnpm verify:mobile
```

`SITE_URL` 可以指定其他预览地址。

## 目录

- `src/app/page.tsx`：页面（中英文：`?lang=en`）。
- `src/components/ShangyuanWorld.tsx` + `.module.css`：三步进度、合并选灯/祝词面板、取景、狸奴 HUD。
- `src/lib/shangyuan/`：场景、状态机、碰撞、布局、水面、特效、音效、调色。
- `src/lib/shangyuan/cat.ts`：狸奴 G0 占位原型（猫、竹筐、橘子、矮棚与动作状态机）。
- `public/models/lantern-river/`：合并后的世界 GLB、船 GLB、碰撞布局 JSON（由 Blender 导出）。
- `public/models/shangyuan/`：早期 Shangyuan 模型；入口牌坊、小舟与河灯模板在运行时复用。
- `public/images/shangyuan/`：进入页封面（来自 `lantern-river` 离线渲染）。
- `scripts/shangyuan/`：截图与试玩脚本（Playwright），共用 `harness.cjs`。
- `../../packages/assets/blender/`：Blender 母版和建模、导出、渲染、校验脚本。
- `../../packages/assets/shangyuan/`：布局、灰模、导出模型、校验日志、预览图。
- `../../packages/assets/lantern-river/`：离线 lookdev 场景、五张 1920×1080 成片、contact sheet 与重建脚本。
- `../../packages/assets/lantern/`、`pavilion/`：可复用的灯笼与亭子资产、渲染和制作简报。

## 场景与碰撞

世界、可行走面和障碍物来自同一份 Blender 场景，避免运行时手写碰撞与美术错位：

- `packages/assets/lantern-river/scripts/build_scene.py` 负责关卡。河宽、店铺退距、桥、广场和码头都写在这里。
- `export_web_world.py` 导出 `world.glb` 与 `layout.json`，三条游船也烘焙进 `world.glb`，位置只在关卡里维护。`layout.json` 包含真实可行走三角形（堤岸、压顶、台阶、广场、拱桥桥面）与障碍物占地；建筑和摊位按人身高度 2.2 m 的真实轮廓取样，屋檐与棚顶不再误挡道路。
- `apps/web/src/lib/shangyuan/collision.ts` 只负责采样：`WalkableGround` 取脚下最高的可行走面，`ObstacleField` 做圆与有向盒的推出，`scene.ts` 以 0.28 m 子步和分轴回退实现贴墙滑动。
- 浏览器内按 `C` 显示碰撞线框：青色为可行走，橙色为阻挡。

重新导出：

```powershell
$blender = 'D:\Workspace\Apps\Scoop\shims\blender.exe'
$root = 'D:\Coding\wowland\packages\assets\lantern-river'
$env:LR_SKIP_RENDER = '1'
& $blender -b --python "$root\scripts\build_scene.py"
& $blender -b "$root\exports\SM_Scene_LanternRiver_Night.blend" `
  --python "$root\scripts\export_web_world.py" -- --draco
Copy-Item "$root\web\world.glb" 'apps\web\public\models\lantern-river\world.glb' -Force
Copy-Item "$root\web\layout.json" 'apps\web\public\models\lantern-river\layout.json' -Force
```

`public/models/**` 是生成资产，已从 Biome 检查中排除。

字体：标题用朱雀仿宋子集（`public/fonts/zhuque-fangsong-subset.woff2`，SIL OFL，许可证在同一目录）。
