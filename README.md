# 上元灯夜（网页预览）

一个可以走进去的宋代水城上元灯会：领灯、猜谜、放河灯，看一场灯会。Next.js 16 + React 19 + three.js。

制作方案见仓库根目录的《桃源上元灯会_制作方案.md》，网页预览的设计与验收记录见 `docs/plans/2026-11-14-shangyuan-lantern-night.md`。

## 运行

```bash
npm install
npm run dev        # http://127.0.0.1:3000/
npm run typecheck
npm run build && npm start
```

## 目录

| 位置 | 内容 |
|---|---|
| `src/app/page.tsx` | 页面（中英文：`?lang=en`） |
| `src/components/ShangyuanWorld.tsx` + `.module.css` | 界面：领灯、灯谜、河灯、祝词、机位 |
| `src/lib/shangyuan/` | 场景（`scene.ts`）、布局数据（`data.ts`）、水面、特效、音效、后期调色 |
| `public/models/shangyuan/` | 24 个 glb 模型（由 Blender 导出） |
| `assets/blender/shangyuan-lantern-night.blend` + `assets/blender/scripts/sy_*.py` | Blender 母版和建模、导出、渲染、校验脚本 |
| `artifacts/shangyuan/` | 布局、灰模、导出模型、校验日志、预览图 |
| `scripts/shangyuan/` | 截图与试玩脚本（Playwright，需先 `npm run dev`；`SITE_URL` 可改地址）；`wprefab/` 是造世界预制件的结构与 Lua 脚本 |
| `docs/validation/2026-11-14-shangyuan/` | 验收截图 |

字体：标题用朱雀仿宋子集（`public/fonts/zhuque-fangsong-subset.woff2`，SIL OFL，许可证在同一目录）。
