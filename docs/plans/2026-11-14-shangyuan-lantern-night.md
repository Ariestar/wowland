# 《上元灯夜》造世界执行计划

日期：2026-11-14。目标：在抖音造世界编辑器交付一个高品质、可漫游、可交互的宋代风格江南水城灯会。用户已确认：高品质模式、Blender 母版为主、单人流程完整即可；本轮直接执行到 G5 再请用户验收。

## 一句话与范围

提一盏灯，过一座桥，把心愿放进一条会发光的河。

- 主路线约 260 m：S1 牌坊领灯 → S2 沿河灯市猜谜 → S3 主桥与灯楼换灯 → S4 埠头选祝词并放灯 → S5 灯楼亮灯与灯会高潮。
- 本轮只做建筑外立面，不做室内；不做自由输入、强制多人协作、亲自打铁花和 NPC 绑骨。
- 本地方案不调用模型/PCG 生成服务，不消耗星光。若后续需要生成服务，先查价并单独征得同意。
- 保留：连续河道、主桥、主灯楼、临水立面、水面倒影、舟船、河灯和完整的明暗节奏。

## 空间与资产边界

Blender 使用米制、Z-up；glTF 导出 Y-up。局部布局：X=0…180，河道中心 Blender Y=0、宽 24 m；北岸主街 Y=18，南岸次街 Y=-18；入口 X=20，主桥 X=90，灯楼 X=98/Y=23，放灯埠头 X=125，南岸表演位 X=140。正式场景导入时统一偏移到 Runtime 合法世界范围，所有世界坐标保持 `[0,255]`。

独立资源边界：

| 资源 ID | 内容 | 烘焙 |
|---|---|---|
| `model-riverbanks` | 河道驳岸、街面、埠头、固定铺地 | 是 |
| `model-paifang` | 入口牌坊与固定装饰 | 结构是，灯笼否 |
| `model-bridge` | 单孔石拱桥、台阶、栏杆 | 是 |
| `model-lantern-tower` | 三层主灯楼结构 | 结构是，灯轮/灯笼/发光层否 |
| `model-shop-01…06` | 六间可独立替换的商铺/茶楼/酒肆 | 结构是，动态灯否 |
| `model-stall-riddle` / `model-stall-tea` | 灯谜摊、汤圆灯笼摊 | 结构是 |
| `model-lantern-array-*` | 分区固定灯笼、灯串与倒影条 | 否 |
| `model-river-lantern-lotus/paperboat/fish` | 三款河灯 | 否 |
| `model-boat` / `model-skiff` | 画舫与小船 | 否 |
| `model-performance` | 南岸表演台 | 结构是 |

母版：`assets/blender/shangyuan-lantern-night.blend`。脚本：`assets/blender/scripts/sy_*.py`。导出与验收产物：`artifacts/shangyuan/`（不覆盖现有小世界文件）。

## 高品质执行合同

1. **代表区域先行**：S3 桥头先完成布局/材质、真实运行打光、特效小样和单区试烘；通过后扩展其余区域。
2. **打光**：读取实际 `scene environment` 合同；天空、反射、曝光和主辅光必须在正式 Runtime 验证。没有可写 `lightData` 时使用正式 Lua `UnityEngine.Light`，不伪造组件。
3. **静态颜色烘焙**：布局与灯光稳定后，Cycles Diffuse Color + Direct + Indirect 烘入非重叠 UV 颜色图；间接光必须参与。保留未烘母版。不得以 AO 代替 GI。
4. **动态排除**：水面、河灯、灯笼、灯轮、烟花/铁花、船和交互灯架不烘焙。动态事件由少量真实点光、Emission、发光贴片与特效补偿。
5. **特效**：从随包模板制作，验证启动、稳定、消散三阶段和正式运行可见性；粒子不替代真实照明。
6. **验收**：同一玩家机位、曝光和环境比较；保存后重开复查。未实测项明确标记，不以导入成功代替视觉验收。

## 交互状态机

`Idle → LanternClaimed → RiddleSolved → RiverLanternSelected → BlessingSelected → Released → TowerSequencePlaying/Completed`

- 领灯：入口 Trigger + 按钮，本地玩家状态。
- 灯谜：三题、每题三选一；答错给提示且可重试，答对获得灯芯。
- 换灯：莲花/纸船/鱼龙三款；按灯芯解锁，灯芯不足时保留莲花灯。
- 放灯：仅在埠头区域内允许；四种预设祝词（平安/团圆/前程/相逢），不开放自由输入。
- 河灯：预摆放、初始隐藏的对象池，放灯后激活并沿预设航道漂移；本地计数与 NPC 环境灯共同形成灯海。
- 高潮：首盏灯放出后触发灯楼逐层亮灯，随后烟花/铁花；支持冷却与重播。特效失败不阻断流程。
- UI：单一动态面板，复用四个选项按钮；横屏先行，移动端竖屏另行实测。

## 平台探针

1. GLB 自发光、材质和实例性能。
2. 实际环境字段、天空/反射资产、曝光和移动端灯光上限。
3. 水面可用路径：环境反射、材质或静态倒影条兜底。
4. `triggerData` + Lua + Runtime UI 的真实输入链路。
5. Effect 模板归档、Lua 引用和播放。
6. AudioClip 发布、绑定和实际播放。
7. 拍照/共享状态能力；本轮不依赖联机。
8. 三角面、draw call、加载时间与帧率定标。

## Web 预览（2026-11-14 交付）

用户决定先在网页预览，不进入抖音编辑器。新增 `/shangyuan` 路由（`noindex`，不进导航）：

- 代码：`src/app/shangyuan/page.tsx`、`src/components/site/ShangyuanWorld.tsx` + `.module.css`、`src/lib/shangyuan/{scene,data,water,effects,audio,types}.ts`。

  **[已过时 · 2026-11-17]** 上面是它还放在宋佳融个人网站代码里时的路径。现在上元是独立项目（本仓库），页面在根路径 `/`：`src/app/page.tsx`、`src/components/ShangyuanWorld.tsx` + `.module.css`、`src/lib/shangyuan/`（原来借用的个人网站 `postFx.ts` 已复制为 `src/lib/shangyuan/postFx.ts`）。见仓库根目录 `README.md`。
- 资产：`public/models/shangyuan/*.glb`（24 个，来自 `artifacts/shangyuan/models`，约 11 MB）；Blender 母版与脚本见上文。
- 玩法：领灯 → 三题灯谜（答错给提示可重试）→ 三款河灯（灯芯解锁）→ 四选祝词 → 放灯 → 灯楼亮灯/打铁花/烟花；6 个机位、留影框、静音、手机方向键。
- 水面为自定义着色器（深蓝水体 + 月光高光 + 河灯竖向倒影带），不依赖平台反射。
- 渲染：three.js + EffectComposer（sanitize → Bloom → Output → 调色），桌面约 60–120 fps、draw call 36–213、三角面 6–13 万；手机模拟 390×844 约 120 fps。
- 验收证据：`docs/validation/2026-11-14-shangyuan/`（15 张，含 6 机位、全流程、打铁花、手机）。

已知限制：浏览器内的碰撞是手写的桥面高度 + 矩形障碍，不含物理引擎；未在真机验证；GI 颜色烘焙与平台内打光仍未做（那是造世界侧的高品质步骤）。

## 当前阻塞与处理

- 项目 `上元灯夜` 已创建，项目目录为 `C:\Users\宋佳融\AppData\Roaming\AI World Creator\projects\project-6971c295-8c0e-478b-8cc8-8e7b6cdfd7d3`。
- 新项目独立实例两次启动均因“独立实例登录状态准备失败”退出；需要用户在可见编辑器完成登录。现有“我的项目”实例保持不动。
- 阻塞期间并行完成 Blender 母版、灰盒、资源导出和 Lua/UI 源码；登录恢复后立即导入运行，不把本地 Blender 效果当作平台验收。

## G5 验收标准

- S1–S4 连通，主路线可走，关键视线中始终能看到水或主灯楼。
- 入口、桥头和埠头有同机位玩家视角截图；代表区材质、比例、通行和落地成立。
- 静态烘焙接收者全部完成并接入，动态排除清单有记录；GI 不是 AO 冒充。
- 领灯、猜谜、换灯、祝词和放灯可由真实输入完成；答错和顺序错误有反馈。
- 河灯可见并漂移，灯楼逐层亮灯；特效不可用时仍有发光/音频降级。
- 保存、重开与同机位复查放到 G6/G7；本轮报告中单列尚未验证项。
