// 《上元灯夜》绑定模板：以 authoring prefab execute --file 提交；不是 Node.js 脚本。
// handles/scriptHandles 必须来自 01 或 scripts.bindings 的真实回执；towerLayers 必须来自真实模型检查。
const CONFIG = {
  handles: {
    host: null,
    releaseTrigger: null,
    tower: null,
    ui: null,
  },
  scriptHandles: {
    gameState: null,
    gameUi: null,
    gameTrigger: null,
    lampTower: null,
    riverLanternPool: null,
  },
  assetUris: {
    towerStepEffect: null,
    towerStepSound: null,
    releaseEffect: null,
    releaseSound: null,
  },
  nodePaths: {
    towerLayers: [],
    poolRoot: "RiverLanternPool",
    spawnAnchor: "ReleaseSpawnAnchor",
  },
  parameters: {
    toastSeconds: 3.5,
    triggerRangeScale: 1,
    towerStepInterval: 0.85,
    towerLightIntensity: 2.4,
    towerLightRange: 5,
    driftDirection: [0, 0, 1],
    driftSpeed: 0.72,
    swayAmplitude: 0.42,
    swayFrequency: 1.35,
    channelLength: 32,
    npcLightIntensity: 1.15,
    npcLightRange: 3.2,
  },
};

function requireHandle(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`CONFIG.${label} 必须填写真实 SDK 回执 handle`);
  }
  return value;
}

for (const [key, value] of Object.entries(CONFIG.handles)) requireHandle(value, `handles.${key}`);
for (const [key, value] of Object.entries(CONFIG.scriptHandles)) {
  requireHandle(value, `scriptHandles.${key}`);
}
if (!Array.isArray(CONFIG.nodePaths.towerLayers) || CONFIG.nodePaths.towerLayers.length === 0
  || CONFIG.nodePaths.towerLayers.some((path) => typeof path !== "string" || path.trim() === "")) {
  throw new Error("CONFIG.nodePaths.towerLayers 必须填写从低到高的真实模型相对路径");
}

function withOptionalAsset(params, key, uri) {
  if (uri !== null && uri !== undefined) {
    if (typeof uri !== "string" || uri.trim() === "") {
      throw new Error(`${key} 必须为真实 URI 或 null`);
    }
    params[key] = { uri };
  }
  return params;
}

async function bindOrUpdate(node, script, params) {
  const page = await scene.scripts.bindings([node], { limit: 50 });
  const existing = page.items.find((item) => item.script === script);
  if (existing) {
    if (existing.readonly) throw new Error(`目标绑定只读：${script}`);
    await scene.scripts.setParams({ bindings: [existing.handle], values: params });
    return { binding: existing.handle, updated: true };
  }
  const bindings = await scene.scripts.bind({ nodes: [node], script, params });
  return { bindings, updated: false };
}

const results = {};
results.gameState = await bindOrUpdate(CONFIG.handles.host, CONFIG.scriptHandles.gameState, {});

const poolParams = {
  PoolRootPath: CONFIG.nodePaths.poolRoot,
  SpawnAnchorPath: CONFIG.nodePaths.spawnAnchor,
  DriftDirection: CONFIG.parameters.driftDirection,
  DriftSpeed: CONFIG.parameters.driftSpeed,
  SwayAmplitude: CONFIG.parameters.swayAmplitude,
  SwayFrequency: CONFIG.parameters.swayFrequency,
  ChannelLength: CONFIG.parameters.channelLength,
  NpcLightIntensity: CONFIG.parameters.npcLightIntensity,
  NpcLightRange: CONFIG.parameters.npcLightRange,
};
withOptionalAsset(poolParams, "ReleaseEffect", CONFIG.assetUris.releaseEffect);
withOptionalAsset(poolParams, "ReleaseSound", CONFIG.assetUris.releaseSound);
results.riverLanternPool = await bindOrUpdate(
  CONFIG.handles.host, CONFIG.scriptHandles.riverLanternPool, poolParams
);

const towerParams = {
  LayerPaths: CONFIG.nodePaths.towerLayers,
  StepInterval: CONFIG.parameters.towerStepInterval,
  LightIntensity: CONFIG.parameters.towerLightIntensity,
  LightRange: CONFIG.parameters.towerLightRange,
};
withOptionalAsset(towerParams, "TowerStepEffect", CONFIG.assetUris.towerStepEffect);
withOptionalAsset(towerParams, "TowerStepSound", CONFIG.assetUris.towerStepSound);
results.lampTower = await bindOrUpdate(CONFIG.handles.tower, CONFIG.scriptHandles.lampTower, towerParams);
results.gameUi = await bindOrUpdate(
  CONFIG.handles.ui, CONFIG.scriptHandles.gameUi, { ToastSeconds: CONFIG.parameters.toastSeconds }
);
results.gameTrigger = await bindOrUpdate(
  CONFIG.handles.releaseTrigger,
  CONFIG.scriptHandles.gameTrigger,
  { TriggerRangeScale: CONFIG.parameters.triggerRangeScale }
);

return {
  bindings: results,
  diagnostics: await scene.document.validate(),
  next: "回读 scripts.bindings、triggerData 与所有 URI/路径参数；通过后再 validate/build/archive 和真实运行验收。",
};
