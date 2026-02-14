local DataStorage = require("datastorage")
local LuaSettings = require("luasettings")
local logger = require("logger")

local GhostwriterSettings = {
  settings = nil,
  data = nil,
}
GhostwriterSettings.__index = GhostwriterSettings

local ROOT_KEY = "ghostwriter"

local DEFAULTS = {
  server_url = "",
  api_token = "",
  download_dir = "",
  last_known_id = "",
  keep_last_n = 30,
  sync_on_suspend = false,
}

local function normalize_server_url(url)
  url = tostring(url or "")
  url = url:gsub("%s+", "")
  url = url:gsub("/*$", "")
  if url:sub(-4) == "/api" then
    url = url:sub(1, -5)
  end
  return url
end

local function clamp_int(value, min_v, max_v)
  local n = tonumber(value)
  if not (n and n == n) then
    return min_v
  end
  if n < min_v then
    return min_v
  end
  if n > max_v then
    return max_v
  end
  return math.floor(n)
end

local function open_settings_handle()
  local path = DataStorage:getSettingsDir() .. "/ghostwriter.lua"
  return LuaSettings:open(path)
end

function GhostwriterSettings:new()
  local obj = setmetatable({}, self)
  obj.settings = open_settings_handle()

  local ok, data = pcall(function()
    return obj.settings:readSetting(ROOT_KEY, {}) or {}
  end)

  if ok then
    obj.data = data
  else
    logger.err("[Ghostwriter] Failed to read settings, using defaults", tostring(data))
    obj.data = {}
  end

  return obj
end

function GhostwriterSettings:save()
  local ok, err = pcall(function()
    self.settings:saveSetting(ROOT_KEY, self.data)
    self.settings:flush()
  end)

  if not ok then
    logger.err("[Ghostwriter] Failed to save settings", tostring(err))
    return false
  end

  return true
end

function GhostwriterSettings:update(patch)
  for k, v in pairs(patch or {}) do
    self.data[k] = v
  end
  return self:save()
end

function GhostwriterSettings:getServerURL()
  return self.data.server_url or DEFAULTS.server_url
end

function GhostwriterSettings:setServerURL(url)
  return self:update({ server_url = normalize_server_url(url) })
end

function GhostwriterSettings:getApiToken()
  return self.data.api_token or DEFAULTS.api_token
end

function GhostwriterSettings:setApiToken(token)
  token = tostring(token or ""):gsub("^%s+", ""):gsub("%s+$", "")
  return self:update({ api_token = token })
end

function GhostwriterSettings:getDownloadDir()
  return self.data.download_dir or DEFAULTS.download_dir
end

function GhostwriterSettings:setDownloadDir(path)
  path = tostring(path or "")
  if path ~= "" and path:sub(-1) ~= "/" then
    path = path .. "/"
  end
  return self:update({ download_dir = path })
end

function GhostwriterSettings:getLastKnownId()
  return self.data.last_known_id or DEFAULTS.last_known_id
end

function GhostwriterSettings:setLastKnownId(id)
  return self:update({ last_known_id = tostring(id or "") })
end

function GhostwriterSettings:getKeepLastN()
  return clamp_int(self.data.keep_last_n or DEFAULTS.keep_last_n, 0, 500)
end

function GhostwriterSettings:setKeepLastN(n)
  return self:update({ keep_last_n = clamp_int(n, 0, 500) })
end

function GhostwriterSettings:getSyncOnSuspendEnabled()
  local value = self.data.sync_on_suspend
  if value == nil then
    return DEFAULTS.sync_on_suspend
  end
  return value == true
end

function GhostwriterSettings:setSyncOnSuspendEnabled(enabled)
  return self:update({ sync_on_suspend = (enabled == true) })
end

return GhostwriterSettings
