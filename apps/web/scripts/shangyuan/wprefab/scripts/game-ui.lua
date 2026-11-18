-- 上元灯夜 Runtime UI；只读 Host 快照、发送操作并管理自身控件。
---@displayName 上元灯夜界面
---@id PENDING_SCRIPTS_CREATE
---@referenceName game-ui.lua
---@start
---@var ToastSeconds:number=3.5
---@name 提示显示秒数
---@desc 新提示在屏幕上方停留的本地时长
---@end

local Time = CS.UnityEngine.Time
local ButtonType = typeof(CS.UnityEngine.UI.Button)
local TextType = typeof(CS.UnityEngine.UI.Text)
local Logger = require("official.core.logger")
local RuntimeScope = require("official.core.runtime_scope")
local logger = Logger.create("shangyuan-ui")
local runtimeScope, runtimeScopeReason = RuntimeScope.from(self)

local HOST_SCRIPT_ID = "game-state.lua"
local PANEL_ROOT = "optionsPanelRoot"
local TOAST_ROOT = "toastRoot"
local host = nil
local listeners = {}
local components = {}
local panelOpen = false
local snapshot = nil
local lastSignature = nil
local lastToastRevision = 0
local toastVisibleUntil = 0
local localToastMessage = nil

local function getGo(nodePath)
  if runtimeScope == nil then return nil end
  return runtimeScope:GetGameObjectByPath(nodePath)
end

local function getUiComponent(nodePath, componentType, label)
  if runtimeScope == nil then return nil end
  local cached = components[nodePath]
  if cached ~= nil and cached[componentType] ~= nil then return cached[componentType] end
  local go, reason = runtimeScope:GetGameObjectByPath(nodePath)
  local component = go ~= nil and go:GetComponent(componentType) or nil
  if component == nil then
    logger:warnOnce("missing-" .. label .. "-" .. nodePath,
      "UI component unavailable", nodePath, tostring(reason or label))
    return nil
  end
  components[nodePath] = cached or {}
  components[nodePath][componentType] = component
  return component
end

local function setText(nodePath, value)
  local text = getUiComponent(nodePath, TextType, "Text")
  if text ~= nil then text.text = tostring(value or "") end
end

local function setActive(nodePath, active)
  local go = getGo(nodePath)
  if go ~= nil and go.activeSelf ~= active then go:SetActive(active) end
end

local function bindButton(nodePath, handler)
  local button = getUiComponent(nodePath, ButtonType, "Button")
  if button == nil then return end
  button.onClick:AddListener(handler)
  table.insert(listeners, { button = button, handler = handler })
end

local function clearListeners()
  for _, item in ipairs(listeners) do
    if item.button ~= nil and item.handler ~= nil then
      item.button.onClick:RemoveListener(item.handler)
    end
  end
  listeners = {}
end

local function readSnapshot()
  if host == nil or type(host.GetDebugState) ~= "function" then return nil end
  local ok, value = pcall(function() return host.GetDebugState() end)
  if not ok or type(value) ~= "table" then
    logger:warnOnce("snapshot-failed", "无法读取上元灯夜状态快照")
    return nil
  end
  return value
end

local function callHost(methodName, argument)
  if host == nil or type(host[methodName]) ~= "function" then
    localToastMessage = "灯夜协调尚未就绪，请稍后重试。"
    toastVisibleUntil = Time.time + ToastSeconds
    return false
  end
  local ok, result = pcall(function()
    if argument == nil then return host[methodName]() end
    return host[methodName](argument)
  end)
  if not ok then
    logger:warn("UI operation failed", methodName, tostring(result))
    localToastMessage = "操作未完成，请再试一次。"
    toastVisibleUntil = Time.time + ToastSeconds
    return false
  end
  return result == true
end

local function signatureFor(value)
  if value == nil then return "nil" end
  return table.concat({
    tostring(value.state), tostring(value.riddleIndex), tostring(value.wickLevel),
    tostring(value.selectedRiverLantern), tostring(value.selectedBlessing),
    tostring(value.releaseZoneOccupied), tostring(value.releasedCount),
    tostring(value.activeRiverLanterns), tostring(value.towerLitLayers),
    tostring(value.toastRevision), tostring(value.panelTitle),
    tostring(value.panelDescription), table.concat(value.options or {}, "|"),
  }, "#")
end

local STATUS_COPY = {
  Idle = { "上元灯夜 · 待领灯", "领一盏灯，猜三则灯谜。" },
  LanternClaimed = { "素灯已领 · 解谜中", "答错可重试；三谜点亮全部灯芯。" },
  RiddleSolved = { "三谜皆解 · 择河灯", "莲花始终可用，锦鲤与宫纱由灯芯解锁。" },
  RiverLanternSelected = { "河灯已择 · 写祝词", "四选一句，把心愿托付给灯。" },
  BlessingSelected = { "祝词已备 · 待放灯", "请走入河畔放灯区。" },
  Released = { "河灯已放", "愿祝词随流水长明。" },
  TowerSequencePlaying = { "灯楼 · 逐层亮灯", "首放河灯，正唤醒层层灯火。" },
  Completed = { "上元灯夜 · 礼成", "灯楼层层皆明，河灯顺流而去。" },
}

local function refresh()
  snapshot = readSnapshot()
  if snapshot == nil then
    setText("statusRoot/statusText", "上元灯夜 · 等待协调")
    setText("statusRoot/hintText", "请确认 UI 位于玩法 Host 的后代层级。")
    setActive(PANEL_ROOT, false)
    setActive("releaseBtn", false)
    return
  end

  local copy = STATUS_COPY[snapshot.state] or STATUS_COPY.Idle
  setText("statusRoot/statusText", copy[1])
  local hint = copy[2]
  if snapshot.state == "LanternClaimed" then
    hint = "灯谜 " .. tostring(snapshot.riddleIndex) .. "/" .. tostring(snapshot.riddleCount)
      .. " · 灯芯 " .. tostring(snapshot.wickLevel) .. "/" .. tostring(snapshot.riddleCount)
  elseif snapshot.state == "BlessingSelected" then
    hint = snapshot.releaseZoneOccupied and "已在放灯区，可以放灯。" or "尚未进入放灯 Trigger。"
  elseif snapshot.state == "TowerSequencePlaying" then
    hint = "已亮 " .. tostring(snapshot.towerLitLayers) .. " 层 · 河上灯影 "
      .. tostring(snapshot.activeRiverLanterns)
  end
  setText("statusRoot/hintText", hint)

  local claimLabels = {
    Idle = "领灯",
    LanternClaimed = "继续灯谜",
    RiddleSolved = "选择河灯",
    RiverLanternSelected = "选择祝词",
  }
  local claimLabel = claimLabels[snapshot.state]
  setActive("claimBtn", claimLabel ~= nil)
  if claimLabel ~= nil then setText("claimBtn/claimBtnText", claimLabel) end
  setActive("releaseBtn", snapshot.state == "BlessingSelected")

  setText(PANEL_ROOT .. "/panelTitle", snapshot.panelTitle)
  setText(PANEL_ROOT .. "/panelDescription", snapshot.panelDescription)
  for index = 1, 4 do
    local optionRoot = PANEL_ROOT .. "/option" .. index .. "Btn"
    local label = snapshot.options ~= nil and snapshot.options[index] or nil
    setActive(optionRoot, label ~= nil)
    if label ~= nil then setText(optionRoot .. "/option" .. index .. "Text", label) end
  end
  setActive(PANEL_ROOT, panelOpen and snapshot.optionCount > 0)

  if snapshot.toastRevision ~= lastToastRevision then
    lastToastRevision = snapshot.toastRevision
    localToastMessage = nil
    toastVisibleUntil = Time.time + ToastSeconds
  end
end

local function chooseOption(index)
  snapshot = readSnapshot()
  if snapshot == nil then return end
  if snapshot.state == "LanternClaimed" then
    callHost("SubmitRiddleAnswer", index)
  elseif snapshot.state == "RiddleSolved" then
    callHost("SelectRiverLantern", index)
  elseif snapshot.state == "RiverLanternSelected" then
    callHost("SelectBlessing", index)
    panelOpen = false
  else
    return
  end
  refresh()
end

function Start()
  if runtimeScope ~= nil then
    local hostScript, reason = runtimeScope:GetRuntimeHostScript(HOST_SCRIPT_ID)
    if hostScript ~= nil then
      host = hostScript
    else
      logger:warn("Runtime Host unavailable", tostring(reason or runtimeScopeReason))
    end
  else
    logger:warn("Runtime Scope unavailable", tostring(runtimeScopeReason))
  end

  bindButton("claimBtn", function()
    snapshot = readSnapshot()
    if snapshot ~= nil and snapshot.state == "Idle" then callHost("ClaimLantern") end
    panelOpen = true
    refresh()
  end)
  bindButton("releaseBtn", function()
    callHost("ReleaseLantern")
    refresh()
  end)
  bindButton(PANEL_ROOT .. "/closePanelBtn", function()
    panelOpen = false
    refresh()
  end)
  for index = 1, 4 do
    bindButton(PANEL_ROOT .. "/option" .. index .. "Btn", function()
      chooseOption(index)
    end)
  end

  panelOpen = false
  setActive(PANEL_ROOT, false)
  setActive(TOAST_ROOT, false)
  refresh()
end

function Update()
  local nextSignature = snapshot ~= nil and signatureFor(snapshot) or nil
  local current = readSnapshot()
  if current ~= nil then nextSignature = signatureFor(current) end
  if nextSignature ~= lastSignature then
    lastSignature = nextSignature
    refresh()
  end

  local message = localToastMessage
  if message == nil and snapshot ~= nil and snapshot.toastRevision > 0 then
    message = snapshot.toastMessage
  end
  local visible = message ~= nil and Time.time < toastVisibleUntil
  setActive(TOAST_ROOT, visible)
  if visible then setText(TOAST_ROOT .. "/toastText", message) end
end

function OnDestroy()
  clearListeners()
  components = {}
  host = nil
  snapshot = nil
end
