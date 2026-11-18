-- 首放河灯后逐层点亮灯楼；灯光、特效和音频均为本机表现。
---@displayName 上元灯楼逐层亮灯
---@id PENDING_SCRIPTS_CREATE
---@referenceName lamp-tower.lua
---@start
---@var LayerPaths:List<string>={}
---@name 灯楼逐层节点路径
---@desc 相对当前灯楼 Model 根、从低到高的完整节点路径；由真实模型检查回填
---@var StepInterval:number=0.85
---@name 每层亮灯间隔
---@desc 相邻两层亮灯之间的秒数；小于等于 0 时使用默认值
---@var LightIntensity:number=2.4
---@name 每层灯光强度
---@var LightRange:number=5
---@name 每层灯光范围
---@desc 每盏本地 Point Light 的米制范围
---@var TowerStepEffect:UnityEngine.GameObject=nil
---@name 每层亮灯特效
---@refFrom asset
---@assetCategory Effect
---@dataType Prefab
---@var TowerStepSound:UnityEngine.AudioClip=nil
---@name 每层亮灯音效
---@refFrom asset
---@assetCategory Music
---@dataType Audio
---@var TowerStepSoundVolume:number=0.75
---@name 每层亮灯音量
---@desc 0–1，0 表示静音
---@var TowerStepSoundMaxDistance:number=18
---@name 每层亮灯最大作用范围
---@desc 距灯楼声源的可听半径，单位米；小于等于 0 时不播放
---@end

local UnityEngine = CS.UnityEngine
local Time = CS.UnityEngine.Time
local Effect = require("official.effect.playback")
local Logger = require("official.core.logger")
local RuntimeScope = require("official.core.runtime_scope")
local logger = Logger.create("shangyuan-tower")
local runtimeScope, runtimeScopeReason = RuntimeScope.from(self)

local HOST_SCRIPT_ID = "game-state.lua"
local host = nil
local towerInterface = nil
local layers = {}
local litLayerCount = 0
local elapsed = 0
local playing = false
local audioSource = nil
local currentClip = nil

local function applySoundSettings()
  if audioSource == nil then return false end
  if currentClip ~= TowerStepSound then
    audioSource:Stop()
    currentClip = TowerStepSound
  end
  audioSource.volume = math.max(0, math.min(1, TowerStepSoundVolume))
  local distance = TowerStepSoundMaxDistance
  if currentClip == nil or audioSource.volume == 0 or distance <= 0 then
    audioSource:Stop()
    return false
  end
  audioSource.minDistance = math.min(1, distance * 0.1)
  audioSource.maxDistance = distance
  return true
end

local function notifyCompleted()
  if host == nil or type(host.NotifyTowerCompleted) ~= "function" then return end
  local ok, err = pcall(function() host.NotifyTowerCompleted() end)
  if not ok then logger:warn("灯楼完成通知失败", tostring(err)) end
end

local function illuminateNextLayer()
  litLayerCount = litLayerCount + 1
  local layer = layers[litLayerCount]
  if layer == nil then return end
  if layer.light ~= nil then layer.light.enabled = true end

  -- 表现失败不影响层计数、后续层或玩法完成通知。
  if TowerStepEffect ~= nil and Effect.isAvailable() then
    local ok, _, reason = pcall(function()
      return Effect.spawn(self, TowerStepEffect, layer.transform.position)
    end)
    if not ok then
      logger:warnOnce("effect-error-" .. tostring(litLayerCount), "灯楼特效调用失败")
    elseif reason ~= nil then
      logger:warnOnce("effect-reason-" .. tostring(litLayerCount), "灯楼特效未播放", tostring(reason))
    end
  end
  if applySoundSettings() then
    local ok, err = pcall(function() audioSource:PlayOneShot(currentClip) end)
    if not ok then logger:warnOnce("audio-error-" .. tostring(litLayerCount), "灯楼音效失败", tostring(err)) end
  end
end

function StartSequence()
  if #layers == 0 then return false end
  if playing then return true end
  if litLayerCount >= #layers then return false end
  elapsed = 0
  playing = true
  return true
end

function GetLitLayerCount()
  return litLayerCount
end

function IsReady()
  return #layers > 0
end

function Start()
  if runtimeScope == nil then
    logger:warn("灯楼 Runtime Scope 不可用", tostring(runtimeScopeReason))
    return
  end

  for index, nodePath in ipairs(LayerPaths) do
    local layerTransform, reason = runtimeScope:GetTransformByPath(nodePath)
    if layerTransform ~= nil then
      local lightGo = UnityEngine.GameObject("TowerLayerLight" .. tostring(index))
      lightGo.transform:SetParent(layerTransform, false)
      lightGo.transform.localPosition = UnityEngine.Vector3(0, 0, 0)
      local light = lightGo:AddComponent(typeof(UnityEngine.Light))
      light.type = UnityEngine.LightType.Point
      light.color = UnityEngine.Color(1, 0.72, 0.36, 1)
      light.intensity = LightIntensity
      light.range = LightRange
      light.shadows = UnityEngine.LightShadows.None
      light.enabled = false
      table.insert(layers, { transform = layerTransform, lightGo = lightGo, light = light })
    else
      logger:warn("灯楼层节点缺失", nodePath, tostring(reason))
    end
  end

  audioSource = self.gameObject:AddComponent(typeof(UnityEngine.AudioSource))
  audioSource.playOnAwake = false
  audioSource.loop = false
  audioSource.spatialBlend = 1
  audioSource.rolloffMode = UnityEngine.AudioRolloffMode.Linear

  local hostScript, reason = runtimeScope:GetRuntimeHostScript(HOST_SCRIPT_ID)
  if hostScript ~= nil and type(hostScript.RegisterTower) == "function" then
    host = hostScript
    towerInterface = {
      StartSequence = StartSequence,
      GetLitLayerCount = GetLitLayerCount,
      IsReady = IsReady,
    }
    host.RegisterTower(towerInterface)
  else
    logger:warn("灯楼无法登记到玩法 Host", tostring(reason))
  end
end

function Update()
  if audioSource ~= nil and audioSource.isPlaying then applySoundSettings() end
  if not playing then return end

  local interval = StepInterval > 0 and StepInterval or 0.85
  elapsed = elapsed + Time.deltaTime
  local targetCount = math.min(#layers, math.floor(elapsed / interval) + 1)
  while litLayerCount < targetCount do illuminateNextLayer() end

  if litLayerCount >= #layers then
    playing = false
    notifyCompleted()
  end
end

function OnDisable()
  if audioSource ~= nil then audioSource:Stop() end
end

function OnDestroy()
  playing = false
  if host ~= nil and towerInterface ~= nil and type(host.UnregisterTower) == "function" then
    pcall(function() host.UnregisterTower(towerInterface) end)
  end
  towerInterface = nil
  host = nil

  for _, layer in ipairs(layers) do
    if layer.lightGo ~= nil then UnityEngine.Object.Destroy(layer.lightGo) end
  end
  layers = {}
  if audioSource ~= nil then
    audioSource:Stop()
    UnityEngine.Object.Destroy(audioSource)
    audioSource = nil
  end
  currentClip = nil
end
