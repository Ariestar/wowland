-- 上元灯夜本机玩法状态机；Host 仅协调当前 WPrefab，不提供网络同步。
---@displayName 上元灯夜状态
---@id PENDING_SCRIPTS_CREATE
---@referenceName game-state.lua
---@start
---@end

local Logger = require("official.core.logger")
local RuntimeScope = require("official.core.runtime_scope")
local logger = Logger.create("shangyuan-state")
local runtimeScope, runtimeScopeReason = RuntimeScope.from(self)

local POOL_SCRIPT_ID = "river-lantern-pool.lua"
local STATE_TRANSITIONS = {
  Idle = { LanternClaimed = true },
  LanternClaimed = { RiddleSolved = true },
  RiddleSolved = { RiverLanternSelected = true },
  RiverLanternSelected = { RiverLanternSelected = true, BlessingSelected = true },
  BlessingSelected = { RiverLanternSelected = true, BlessingSelected = true, Released = true },
  Released = { TowerSequencePlaying = true },
  TowerSequencePlaying = { Completed = true },
  -- 礼成后可再择一盏河灯，重走选灯与祝词；灯楼只由首放触发。
  Completed = { RiverLanternSelected = true },
}

local RIDDLES = {
  {
    title = "灯谜 · 其一",
    question = "有骨无肉，有衣无身；一点灯芯，照彻长街。打一上元物。",
    options = { "花灯", "纸船", "团扇" },
    answer = 1,
  },
  {
    title = "灯谜 · 其二",
    question = "汴京御街扎起层层彩结，如山似火。打一宋代灯会景观。",
    options = { "冰嬉", "灯山", "秋社" },
    answer = 2,
  },
  {
    title = "灯谜 · 其三",
    question = "稼轩写道：东风夜放花千树，更吹落、星如雨。写的是哪一夜？",
    options = { "中秋夜", "寒食夜", "上元夜" },
    answer = 3,
  },
}

local RIVER_LANTERNS = {
  { name = "莲花灯", requiredWick = 0 },
  { name = "锦鲤灯", requiredWick = 1 },
  { name = "宫纱灯", requiredWick = 3 },
}

local BLESSINGS = {
  "岁岁平安，灯火长明",
  "所愿皆成，所行皆坦",
  "家人闲坐，灯火可亲",
  "前程似锦，步步生光",
}

local state = "Idle"
local riddleIndex = 0
-- 灯芯只在一次答对时增长；答错过的题不再贡献灯芯，因此宫纱灯可能保持锁定。
local wickLevel = 0
local riddleAttempts = {}
local selectedRiverLantern = 0
local selectedBlessing = 0
local releaseZoneOccupied = false
local releasedCount = 0
local toastRevision = 0
local toastMessage = ""
local tower = nil
local firstReleaseStarted = false

local function transition(nextState)
  local allowed = STATE_TRANSITIONS[state]
  if allowed == nil or allowed[nextState] ~= true then
    logger:warn("invalid state transition", state, nextState)
    return false
  end
  state = nextState
  return true
end

local function setToast(message)
  toastRevision = toastRevision + 1
  toastMessage = tostring(message)
end

local function getPool()
  if runtimeScope == nil then
    return nil, runtimeScopeReason
  end
  local pool, reason = runtimeScope:GetScript(POOL_SCRIPT_ID)
  if pool == nil or type(pool.ReleaseLantern) ~= "function" then
    return nil, reason or "river-pool-unavailable"
  end
  if type(pool.IsReady) == "function" and pool.IsReady() ~= true then
    return nil, "river-pool-not-ready"
  end
  return pool, nil
end

local function beginTowerSequence()
  if tower == nil or type(tower.StartSequence) ~= "function" then
    return false
  end
  local ok, started = pcall(function()
    return tower.StartSequence()
  end)
  return ok and started == true
end

-- 灯楼 Start 完成后登记纯 Lua 接口表；重复登记替换同一接口。
function RegisterTower(interfaceTable)
  if type(interfaceTable) ~= "table" or type(interfaceTable.StartSequence) ~= "function" then
    return false
  end
  tower = interfaceTable
  if state == "TowerSequencePlaying" then
    beginTowerSequence()
  end
  return true
end

function UnregisterTower(interfaceTable)
  if tower == interfaceTable then
    tower = nil
  end
end

function IsReady()
  return true
end

function ClaimLantern()
  if state ~= "Idle" then
    setToast("灯已在手，请继续当前灯夜流程。")
    return false
  end
  if not transition("LanternClaimed") then return false end
  riddleIndex = 1
  wickLevel = 0
  riddleAttempts = {}
  setToast("领到一盏素灯，先解三则灯谜。")
  return true
end

function SubmitRiddleAnswer(choice)
  if state ~= "LanternClaimed" or riddleIndex < 1 or riddleIndex > #RIDDLES then
    setToast("当前没有待答灯谜。")
    return false
  end
  if type(choice) ~= "number" or choice % 1 ~= 0 then return false end
  local riddle = RIDDLES[riddleIndex]
  local attempts = (riddleAttempts[riddleIndex] or 0) + 1
  riddleAttempts[riddleIndex] = attempts
  if choice ~= riddle.answer then
    setToast("谜底未中，再想一想；本题仍可重试。")
    return false
  end

  if attempts == 1 then
    wickLevel = wickLevel + 1
  end
  if riddleIndex < #RIDDLES then
    riddleIndex = riddleIndex + 1
    setToast("答对了。下一则灯谜。")
    return true
  end

  if not transition("RiddleSolved") then return false end
  setToast("三谜皆解，灯芯 " .. tostring(wickLevel) .. "/" .. tostring(#RIDDLES) .. "，可择河灯。")
  return true
end

function SelectRiverLantern(index)
  if state ~= "RiddleSolved" and state ~= "RiverLanternSelected"
    and state ~= "BlessingSelected" and state ~= "Completed" then
    setToast("请先解完灯谜，再选河灯。")
    return false
  end
  if type(index) ~= "number" or index % 1 ~= 0 or RIVER_LANTERNS[index] == nil then
    return false
  end
  local lantern = RIVER_LANTERNS[index]
  if index ~= 1 and wickLevel < lantern.requiredWick then
    setToast(lantern.name .. "需要灯芯 " .. tostring(lantern.requiredWick)
      .. "，当前 " .. tostring(wickLevel) .. "；莲花灯始终可用。")
    return false
  end
  selectedRiverLantern = index
  selectedBlessing = 0
  if state ~= "RiverLanternSelected" and not transition("RiverLanternSelected") then return false end
  setToast("已选" .. lantern.name .. "，再择一句祝词。")
  return true
end

function SelectBlessing(index)
  if state ~= "RiverLanternSelected" and state ~= "BlessingSelected" then
    setToast("请先选一款河灯。")
    return false
  end
  if type(index) ~= "number" or index % 1 ~= 0 or BLESSINGS[index] == nil then
    return false
  end
  selectedBlessing = index
  if state ~= "BlessingSelected" and not transition("BlessingSelected") then return false end
  setToast("祝词已写好，请走入河畔放灯区。")
  return true
end

-- 只由放灯 Trigger 的本地 Actor 成对回调维护；不是联网状态。
function SetReleaseZoneOccupied(occupied)
  releaseZoneOccupied = occupied == true
end

function ReleaseLantern()
  if state ~= "BlessingSelected" then
    setToast("请先完成灯谜、河灯与祝词选择。")
    return false
  end
  if not releaseZoneOccupied then
    setToast("请站在河畔放灯 Trigger 内再放灯。")
    return false
  end

  local pool, poolReason = getPool()
  if pool == nil then
    setToast("河灯池尚未就绪：" .. tostring(poolReason))
    return false
  end
  local ok, released, reason = pcall(function()
    return pool.ReleaseLantern(selectedRiverLantern, selectedBlessing, releasedCount + 1)
  end)
  if not ok or released ~= true then
    setToast("本次未能放灯：" .. tostring(reason or "请稍后重试"))
    return false
  end

  if not transition("Released") then return false end
  releasedCount = releasedCount + 1
  setToast("河灯入水，愿" .. BLESSINGS[selectedBlessing] .. "。")

  if not firstReleaseStarted then
    firstReleaseStarted = true
    if transition("TowerSequencePlaying") then
      -- 灯楼缺失或拒绝启动时不阻塞玩家：直接礼成，避免状态机停在播放中。
      if not beginTowerSequence() and transition("Completed") then
        setToast("河灯已放；灯楼未接入，本次按礼成结束。")
      end
    end
  else
    -- 后续放灯不再启动灯楼，直接回到可选灯状态。
    if not transition("RiverLanternSelected") then return true end
  end
  return true
end

function NotifyTowerCompleted()
  if state ~= "TowerSequencePlaying" then return false end
  if not transition("Completed") then return false end
  setToast("灯楼层层皆明，上元灯夜礼成。")
  return true
end

-- 供 UI 与 runtime lua 探针读取的小型快照；不暴露内部可变表。
function GetDebugState()
  local panelTitle = ""
  local panelDescription = ""
  local options = {}
  if state == "LanternClaimed" and RIDDLES[riddleIndex] ~= nil then
    local riddle = RIDDLES[riddleIndex]
    panelTitle = riddle.title
    panelDescription = riddle.question .. "（答错可重试）"
    options = { riddle.options[1], riddle.options[2], riddle.options[3] }
  elseif state == "RiddleSolved" then
    panelTitle = "择一款河灯"
    panelDescription = "莲花灯始终可用；锦鲤灯需灯芯 1，宫纱灯需灯芯 3（一次答对才计灯芯）。"
    for index, lantern in ipairs(RIVER_LANTERNS) do
      local lockText = (index == 1 or wickLevel >= lantern.requiredWick) and " · 可用" or " · 未解锁"
      options[index] = lantern.name .. lockText
    end
  elseif state == "RiverLanternSelected" then
    panelTitle = "择一句祝词"
    panelDescription = "祝词将随所选河灯入水；此后请走入河畔放灯区。"
    options = { BLESSINGS[1], BLESSINGS[2], BLESSINGS[3], BLESSINGS[4] }
  end

  local activeCount = 0
  local pool = getPool()
  if pool ~= nil and type(pool.GetActiveCount) == "function" then
    local ok, count = pcall(function() return pool.GetActiveCount() end)
    if ok and type(count) == "number" then activeCount = count end
  end
  local litLayers = 0
  if tower ~= nil and type(tower.GetLitLayerCount) == "function" then
    local ok, count = pcall(function() return tower.GetLitLayerCount() end)
    if ok and type(count) == "number" then litLayers = count end
  end

  return {
    state = state,
    riddleIndex = riddleIndex,
    riddleCount = #RIDDLES,
    wickLevel = wickLevel,
    selectedRiverLantern = selectedRiverLantern,
    selectedBlessing = selectedBlessing,
    releaseZoneOccupied = releaseZoneOccupied,
    releasedCount = releasedCount,
    activeRiverLanterns = activeCount,
    towerReady = tower ~= nil,
    towerLitLayers = litLayers,
    toastRevision = toastRevision,
    toastMessage = toastMessage,
    panelTitle = panelTitle,
    panelDescription = panelDescription,
    options = options,
    optionCount = #options,
    scopeAvailable = runtimeScope ~= nil,
  }
end

function OnDestroy()
  tower = nil
  releaseZoneOccupied = false
end
