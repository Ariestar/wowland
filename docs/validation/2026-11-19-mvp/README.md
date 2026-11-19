# MVP 验收证据（2026-11-19）

对应 PRD v1.0 与 `docs/plans/2026-11-19-mvp-vertical-slice.md`。
截图与原始 `report.json` 属于本地产物，不入库；本文件记录可复现的结论与命令。

## 环境

- Windows 11 · Node 24 · pnpm 12.22 · Next.js 16.4.6
- 浏览器：Chrome（Playwright headless，GPU angle/d3d11）
- 预览地址：`http://127.0.0.1:3100`（3000 端口被本机其他项目占用）

## 命令与结果

| 命令 | 覆盖 | 结果 |
|---|---|---|
| `pnpm verify` | typecheck + Biome + build | 通过（0 error；7 条既有 warning） |
| `pnpm verify:flow` | 主线全流程 + 猫形 | 通过，0 页面错误 |
| `pnpm verify:states` | 锁定原因、重复交互、答错重开、失焦恢复 | 20/20 |
| `pnpm verify:retry` | 加载失败与原地重试 | 6/6 |
| `pnpm verify:combos` | 3 款 × 4 祝词 | 12/12 |
| `pnpm verify:limits` | 5 盏上限、冷却、60s 回收 | 8/8 |
| `pnpm verify:landscape` | 844×390 完整主线 | 15/15 |
| `pnpm verify:touch` | 触屏按住/取消/拖拽 | 4/4 |
| `pnpm verify:soak`（10 分钟） | 连续游玩与资源稳定性 | 10/10 |

## 10 分钟压测数据

```
minutes 10 · cycles 117 · releases 40 · photos 117 · catTrips 58
geometries 118 → 118 · textures 194 → 194 · drawCalls 199 → 207
playerLanterns ≤ 5 · lanterns ≤ 70 · errors [] · fps 75
inputRecovered true · catModeOff true
```

## 真机/真人待办（本轮无法替代）

- 中端安卓真机：低画质画质档、10 分钟连续试玩、触屏安全区
- 5 名首次玩家观察（PRD §14.2）
- 正式资产替换（A03/A06/A07/A09、猫与动画）
- 造世界平台移植与发布（PRD 第 15 章）

## 复现

```powershell
pnpm install
pnpm --filter @wowland/web exec next dev --port 3100
$env:SITE_URL = 'http://127.0.0.1:3100'
pnpm verify:flow
pnpm verify:states
pnpm verify:retry
pnpm verify:combos
pnpm verify:landscape
pnpm verify:touch
pnpm verify:limits      # 约 2–3 分钟
$env:SOAK_MINUTES = '10'
pnpm verify:soak
```
