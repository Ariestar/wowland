-- 河畔放灯区域；仅本地 Actor 的真实进入/离开事件更新 Host 门控。
---@displayName 放灯区域检测
---@id PENDING_SCRIPTS_CREATE
---@referenceName game-trigger.lua
---@start
---@var TriggerRangeScale:number=1
---@name 触发范围倍率
---@desc 基于场景中已保存的唯一 Box Trigger 等比缩放
---@group 交互
---@end

local Logger = require("official.core.logger")
local RuntimeScope = require("official.core.runtime_scope")
local Trigger = require("official.interaction.trigger")
local logger = Logger.create("shangyuan-trigger")
local runtimeScope, runtimeScopeReason = RuntimeScope.from(self)
Trigger.applyRangeScale(self, TriggerRangeScale)

local HOST_SCRIPT_ID = "game-state.lua"
local host = nil

local function setOccupied(occupied)
  if host == nil or type(host.SetReleaseZoneOccupied) ~= "function" then
    logger:warnOnce("host-unavailable", "放灯区域无法联系玩法 Host", tostring(runtimeScopeReason))
    return false
  end
  host.SetReleaseZoneOccupied(occupied)
  return true
end

function Start()
  if runtimeScope ~= nil then
    local hostScript, reason = runtimeScope:GetRuntimeHostScript(HOST_SCRIPT_ID)
    if hostScript ~= nil then
      host = hostScript
    else
      logger:warn("放灯 Host 查询失败", tostring(reason))
    end
  end
  setOccupied(false)
end

function OnActorTriggerEnter(actor)
  if actor == nil or actor.isLocal ~= true then return end
  setOccupied(true)
end

function OnActorTriggerExit(actor)
  if actor == nil or actor.isLocal ~= true then return end
  setOccupied(false)
end

function OnDisable()
  setOccupied(false)
end

function OnDestroy()
  setOccupied(false)
  host = nil
end
