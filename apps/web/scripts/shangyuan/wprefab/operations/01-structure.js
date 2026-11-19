// 《上元灯夜》结构模板：以 authoring prefab execute --file 提交；不是 Node.js 脚本。
// 先填 CONFIG 中真实 archive URI。任一 URI 缺失会在首次修改前终止。
const CONFIG = {
  assetUris: {
    towerModel: null,
    riverLanternModels: { lotus: null, koi: null, palace: null },
    runtimeUi: null,
  },
  nodeNames: {
    host: "上元灯夜",
    releaseTrigger: "ReleaseTrigger",
    poolRoot: "RiverLanternPool",
    spawnAnchor: "ReleaseSpawnAnchor",
    tower: "灯楼",
  },
  transforms: {
    releaseTriggerPosition: { x: 0, y: 1, z: 4 },
    spawnAnchorPosition: { x: 0, y: 0.15, z: 4 },
    poolStagingOrigin: { x: 0, y: 0, z: 0 },
    poolStagingSpacing: 1.25,
  },
  releaseBox: {
    center: { x: 0, y: 0, z: 0 },
    size: { x: 4, y: 2.5, z: 4 },
  },
  scriptPaths: [
    "game-state.lua",
    "game-ui.lua",
    "game-trigger.lua",
    "lamp-tower.lua",
    "river-lantern-pool.lua",
  ],
};

function requireUri(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`CONFIG.assetUris.${label} 必须填写真实 archive 返回 URI`);
  }
  return value;
}

requireUri(CONFIG.assetUris.towerModel, "towerModel");
requireUri(CONFIG.assetUris.riverLanternModels.lotus, "riverLanternModels.lotus");
requireUri(CONFIG.assetUris.riverLanternModels.koi, "riverLanternModels.koi");
requireUri(CONFIG.assetUris.riverLanternModels.palace, "riverLanternModels.palace");
requireUri(CONFIG.assetUris.runtimeUi, "runtimeUi");

const existing = await scene.nodes.query(
  { name: { equals: CONFIG.nodeNames.host } },
  { fields: ["handle", "name"], limit: 1 }
);
if (existing.items.length > 0) {
  throw new Error("已存在同名 Host；请查询现状，勿重复执行结构创建");
}

const host = await scene.nodes.create({ name: CONFIG.nodeNames.host, parent: null });
await scene.scripts.setScopeRole({ nodes: [host], role: "host" });

const releaseTrigger = await scene.nodes.create({
  name: CONFIG.nodeNames.releaseTrigger,
  parent: host,
});
await scene.scripts.setScopeRole({ nodes: [releaseTrigger], role: "resource" });
await scene.transforms.set({
  nodes: [releaseTrigger],
  value: { position: CONFIG.transforms.releaseTriggerPosition },
  space: "local",
  scope: "subtree",
});
// triggerData 的数组签名与 box 字段来自当前安装资料；执行前仍须用实际 schema 核验。
await scene.components.add({
  nodes: [releaseTrigger],
  type: "triggerData",
  values: [{
    shape: "box",
    enabled: true,
    center: CONFIG.releaseBox.center,
    size: CONFIG.releaseBox.size,
  }],
});

const spawnAnchor = await scene.nodes.create({
  name: CONFIG.nodeNames.spawnAnchor,
  parent: host,
});
await scene.transforms.set({
  nodes: [spawnAnchor],
  value: { position: CONFIG.transforms.spawnAnchorPosition },
  space: "local",
  scope: "subtree",
});

const towerResult = await scene.assets.instantiateModel({
  resource: CONFIG.assetUris.towerModel,
  parent: host,
  name: CONFIG.nodeNames.tower,
});
const tower = towerResult.root;

const poolRoot = await scene.nodes.create({ name: CONFIG.nodeNames.poolRoot, parent: host });
const poolInstances = [];
const styles = [
  { key: "lotus", prefix: "Lotus", uri: CONFIG.assetUris.riverLanternModels.lotus },
  { key: "koi", prefix: "Koi", uri: CONFIG.assetUris.riverLanternModels.koi },
  { key: "palace", prefix: "Palace", uri: CONFIG.assetUris.riverLanternModels.palace },
];
for (let styleIndex = 0; styleIndex < styles.length; styleIndex += 1) {
  const style = styles[styleIndex];
  for (let index = 1; index <= 20; index += 1) {
    const suffix = String(index).padStart(2, "0");
    const instanceResult = await scene.assets.instantiateModel({
      resource: style.uri,
      parent: poolRoot,
      name: `${style.prefix}${suffix}`,
    });
    const root = instanceResult.root;
    const stagingIndex = styleIndex * 20 + index - 1;
    const position = {
      x: CONFIG.transforms.poolStagingOrigin.x
        + (stagingIndex % 5) * CONFIG.transforms.poolStagingSpacing,
      y: CONFIG.transforms.poolStagingOrigin.y,
      z: CONFIG.transforms.poolStagingOrigin.z
        + Math.floor(stagingIndex / 5) * CONFIG.transforms.poolStagingSpacing,
    };
    await scene.transforms.set({
      nodes: [root], value: { position }, space: "local", scope: "subtree",
    });
    await scene.nodes.update([root], { active: false });
    poolInstances.push({ style: style.key, index, root });
  }
}

const uiResult = await scene.assets.instantiateUI({
  resource: CONFIG.assetUris.runtimeUi,
  parent: host,
});
const ui = uiResult.root;

const scriptDefinitions = {};
for (const path of CONFIG.scriptPaths) {
  const created = await scene.scripts.create({ path });
  scriptDefinitions[path] = {
    handle: created.handle,
    filePath: created.filePath,
    referenceName: created.referenceName,
  };
}

return {
  handles: { host, releaseTrigger, spawnAnchor, tower, poolRoot, ui },
  poolInstanceCount: poolInstances.length,
  poolInstances,
  scriptDefinitions,
  diagnostics: await scene.document.validate(),
  next: "保留 scripts.create 生成的 ---@id/---@referenceName，将五份 Lua 正文写入返回 filePath，再填写 02-bindings.js 的 CONFIG。",
};
