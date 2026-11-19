-- 60 个预摆放河灯的本地对象池；只激活既有实例，不动态 Spawn。
---@displayName 上元河灯池
---@id PENDING_SCRIPTS_CREATE
---@referenceName river-lantern-pool.lua
---@start
---@var PoolRootPath:string="RiverLanternPool"
---@name 河灯池节点路径
---@desc 相对玩法 Host 根的完整路径；其下每款预摆放 20 个实例
---@var SpawnAnchorPath:string="ReleaseSpawnAnchor"
---@name 放灯起点路径
---@desc 相对玩法 Host 根的完整路径；同时定义航道局部方向与声源位置
---@var DriftDirection:Vector3=(0,0,1)
---@name 航道漂流方向
---@desc 放灯起点局部坐标中的固定水平方向
---@var DriftSpeed:number=0.72
---@name 漂移速度
---@desc 每秒沿固定方向前进的米数
---@var SwayAmplitude:number=0.42
---@name 正弦横摆幅度
---@desc 相对航道中心线的最大横向米数
---@var SwayFrequency:number=1.35
---@name 正弦横摆频率
---@desc 每秒正弦相位增量对应的弧度系数
---@var ChannelLength:number=32
---@name 航道回收长度
---@desc 沿漂流方向达到此米数后隐藏并回收实例
---@var NpcLightIntensity:number=1.15
---@name 河灯环境光强度
---@desc 本地河灯为周围角色与 NPC 环境提供的 Point Light 强度
---@var NpcLightRange:number=3.2
---@name 河灯环境光范围
---@desc 每盏河灯本地 Point Light 的米制范围
---@var ReleaseEffect:UnityEngine.GameObject=nil
---@name 放灯特效
---@refFrom asset
---@assetCategory Effect
---@dataType Prefab
---@var ReleaseSound:UnityEngine.AudioClip=nil
---@name 放灯音效
---@refFrom asset
---@assetCategory Music
---@dataType Audio
---@var ReleaseSoundVolume:number=0.8
---@name 放灯音量
---@desc 0–1，0 表示静音
---@var ReleaseSoundMaxDistance:number=12
---@name 放灯最大作用范围
---@desc 距放灯起点的可听半径，单位米；小于等于 0 时不播放
---@end

local UnityEngine = CS.UnityEngine
local Time = CS.UnityEngine.Time
local Effect = require("official.effect.playback")
local Logger = require("official.core.logger")
local RuntimeScope = require("official.core.runtime_scope")
local logger = Logger.create("shangyuan-river-pool")
local runtimeScope, runtimeScopeReason = RuntimeScope.from(self)

local MAX_PER_STYLE = 20
local STYLE_DEFINITIONS = {
  { prefix = "Lotus", name = "莲花灯" },
  { prefix = "Koi", name = "锦鲤灯" },
  { prefix = "Palace", name = "宫纱灯" },
}
local records = {}
local recordsByStyle = { {}, {}, {} }
local spawnAnchor = nil
local audioSource = nil
local currentClip = nil
local activeCount = 0
local ready = false

local function applySoundSettings()
  if audioSource == nil then return false end
  if currentClip ~= ReleaseSound then
    audioSource:Stop()
    currentClip = ReleaseSound
  end
  audioSource.volume = math.max(0, math.min(1, ReleaseSoundVolume))
  local distance = ReleaseSoundMaxDistance
  if currentClip == nil or audioSource.volume == 0 or distance <= 0 then
    audioSource:Stop()
    return false
  end
  audioSource.minDistance = math.min(1, distance * 0.1)
  audioSource.maxDistance = distance
  return true
end

local function destroyAmbientLight(record)
  if record.lightGo ~= nil then
    UnityEngine.Object.Destroy(record.lightGo)
    record.lightGo = nil
  end
end

local function recycle(record)
  if record == nil or not record.active then return end
  record.active = false
  activeCount = math.max(0, activeCount - 1)
  destroyAmbientLight(record)
  if record.gameObject ~= nil then record.gameObject:SetActive(false) end
  if record.transform ~= nil then record.transform.localPosition = record.initialLocalPosition end
  record.origin = nil
  record.direction = nil
  record.lateral = nil
end

local function recycleAll()
  for _, record in ipairs(records) do recycle(record) end
  activeCount = 0
end

local function createAmbientLight(record)
  if record.lightGo ~= nil then return end
  local lightGo = UnityEngine.GameObject("RiverLanternAmbientLight")
  lightGo.transform:SetParent(record.transform, false)
  lightGo.transform.localPosition = UnityEngine.Vector3(0, 0.18, 0)
  local light = lightGo:AddComponent(typeof(UnityEngine.Light))
  light.type = UnityEngine.LightType.Point
  light.color = UnityEngine.Color(1, 0.64, 0.28, 1)
  light.intensity = NpcLightIntensity
  light.range = NpcLightRange
  light.shadows = UnityEngine.LightShadows.None
  record.lightGo = lightGo
end

local function findInactive(styleIndex)
  for _, record in ipairs(recordsByStyle[styleIndex]) do
    if not record.active then return record end
  end
  return nil
end

local function readDirection()
  if spawnAnchor == nil then return nil, nil, "spawn-anchor-missing" end
  local direction = spawnAnchor:TransformDirection(DriftDirection)
  local length = math.sqrt(direction.x * direction.x + direction.y * direction.y + direction.z * direction.z)
  local horizontalLength = math.sqrt(direction.x * direction.x + direction.z * direction.z)
  if length <= 0.0001 or horizontalLength <= 0.0001 then
    return nil, nil, "drift-direction-not-horizontal"
  end
  local forward = UnityEngine.Vector3(direction.x / length, direction.y / length, direction.z / length)
  local lateral = UnityEngine.Vector3(-direction.z / horizontalLength, 0, direction.x / horizontalLength)
  return forward, lateral, nil
end

-- 成功仅表示一个既有实例已激活；特效与声音失败仍返回成功。
function ReleaseLantern(styleIndex, blessingIndex, sequence)
  if not ready or spawnAnchor == nil then return false, "river-pool-not-ready" end
  if type(styleIndex) ~= "number" or recordsByStyle[styleIndex] == nil then
    return false, "invalid-lantern-style"
  end
  local record = findInactive(styleIndex)
  if record == nil then return false, "该款河灯正在航道中，请等待回收" end

  local forward, lateral, directionReason = readDirection()
  if forward == nil then return false, directionReason end
  local lane = ((sequence or 1) % 3) - 1
  local laneOffset = lane * 0.55
  local anchorPosition = spawnAnchor.position
  local origin = UnityEngine.Vector3(
    anchorPosition.x + lateral.x * laneOffset,
    anchorPosition.y,
    anchorPosition.z + lateral.z * laneOffset
  )

  record.origin = origin
  record.direction = forward
  record.lateral = lateral
  record.elapsed = 0
  record.phase = (sequence or 1) * 0.73
  record.blessingIndex = blessingIndex
  record.active = true
  record.transform.position = origin
  record.gameObject:SetActive(true)
  createAmbientLight(record)
  activeCount = activeCount + 1

  if ReleaseEffect ~= nil and Effect.isAvailable() then
    local ok, _, reason = pcall(function()
      return Effect.spawn(self, ReleaseEffect, origin)
    end)
    if not ok then
      logger:warnOnce("release-effect-error", "放灯特效调用失败")
    elseif reason ~= nil then
      logger:warnOnce("release-effect-reason", "放灯特效未播放", tostring(reason))
    end
  end
  if applySoundSettings() then
    local ok, err = pcall(function() audioSource:PlayOneShot(currentClip) end)
    if not ok then logger:warnOnce("release-audio-error", "放灯音效失败", tostring(err)) end
  end
  return true, nil
end

function GetActiveCount()
  return activeCount
end

function GetCapacity()
  return #records
end

function IsReady()
  return ready
end

function Start()
  if runtimeScope == nil then
    logger:warn("河灯池 Runtime Scope 不可用", tostring(runtimeScopeReason))
    return
  end

  local anchor, anchorReason = runtimeScope:GetTransformByPath(SpawnAnchorPath)
  spawnAnchor = anchor
  if spawnAnchor == nil then
    logger:warn("放灯起点缺失", SpawnAnchorPath, tostring(anchorReason))
  end

  for styleIndex, definition in ipairs(STYLE_DEFINITIONS) do
    for index = 1, MAX_PER_STYLE do
      local nodePath = PoolRootPath .. "/" .. definition.prefix .. string.format("%02d", index)
      local go, reason = runtimeScope:GetGameObjectByPath(nodePath)
      if go ~= nil then
        go:SetActive(false)
        local record = {
          gameObject = go,
          transform = go.transform,
          initialLocalPosition = go.transform.localPosition,
          styleIndex = styleIndex,
          active = false,
          lightGo = nil,
          elapsed = 0,
          phase = 0,
        }
        table.insert(records, record)
        table.insert(recordsByStyle[styleIndex], record)
      else
        logger:warnOnce("missing-" .. nodePath, "预摆放河灯节点缺失", nodePath, tostring(reason))
      end
    end
  end

  if spawnAnchor ~= nil then
    audioSource = spawnAnchor.gameObject:AddComponent(typeof(UnityEngine.AudioSource))
    audioSource.playOnAwake = false
    audioSource.loop = false
    audioSource.spatialBlend = 1
    audioSource.rolloffMode = UnityEngine.AudioRolloffMode.Linear
  end
  ready = spawnAnchor ~= nil and #records > 0
end

function Update()
  if audioSource ~= nil and audioSource.isPlaying then applySoundSettings() end
  for _, record in ipairs(records) do
    if record.active then
      record.elapsed = record.elapsed + Time.deltaTime
      local distance = record.elapsed * math.max(0, DriftSpeed)
      if distance >= math.max(0.1, ChannelLength) then
        recycle(record)
      else
        local sway = math.sin(record.elapsed * SwayFrequency + record.phase) * SwayAmplitude
        record.transform.position = UnityEngine.Vector3(
          record.origin.x + record.direction.x * distance + record.lateral.x * sway,
          record.origin.y + record.direction.y * distance,
          record.origin.z + record.direction.z * distance + record.lateral.z * sway
        )
      end
    end
  end
end

function OnDisable()
  recycleAll()
  if audioSource ~= nil then audioSource:Stop() end
end

function OnDestroy()
  ready = false
  recycleAll()
  records = {}
  recordsByStyle = { {}, {}, {} }
  spawnAnchor = nil
  if audioSource ~= nil then
    audioSource:Stop()
    UnityEngine.Object.Destroy(audioSource)
    audioSource = nil
  end
  currentClip = nil
end
