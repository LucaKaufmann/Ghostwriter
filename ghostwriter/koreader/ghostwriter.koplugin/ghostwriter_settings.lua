local DataStorage = require("datastorage")
local LuaSettings = require("luasettings")
local logger = require("logger")
local lfs = require("libs/libkoreader-lfs")

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

local function same_value(a, b, seen)
  if type(a) ~= type(b) then return false end
  if type(a) ~= "table" then return a == b end
  seen = seen or {}
  if seen[a] then return false end
  seen[a] = true
  for key, value in pairs(a) do
    if not same_value(value, b[key], seen) then return false end
  end
  for key in pairs(b) do
    if a[key] == nil then return false end
  end
  seen[a] = nil
  return true
end

function GhostwriterSettings:new()
  local obj = setmetatable({}, self)
  obj.settings = open_settings_handle()

  local ok, data = pcall(function()
    return obj.settings:readSetting(ROOT_KEY, {}) or {}
  end)

  if ok and type(data) == "table" then
    obj.data = data
  else
    logger.err("[Ghostwriter] Failed to read settings, using defaults", tostring(data))
    obj.data = {}
  end

  local path = obj.settings.file
  if lfs.symlinkattributes(path) then
    local chunk = loadfile(path)
    local valid, primary = chunk and pcall(chunk)
    if not valid or type(primary) ~= "table" or type(primary[ROOT_KEY]) ~= "table" then
      -- LuaSettings.open silently falls back to .old. Preserve connection
      -- details, but never adopt ownership/cursor state from that backup.
      obj.data.owned_downloads = nil
      obj.data.cursors = nil
      obj.data.last_known_id = nil
      logger.err("[Ghostwriter] Primary settings file is invalid; ownership reset")
    end
  end

  return obj
end

function GhostwriterSettings:save()
  local ok, err = pcall(function()
    self.settings:saveSetting(ROOT_KEY, self.data)
    self.settings:flush()
    -- KOReader's LuaSettings.flush returns `self` even if writeToFile fails.
    -- Read the primary file, not LuaSettings.open's backup fallback, before
    -- treating ownership or cursor updates as durable.
    local chunk = assert(loadfile(self.settings.file))
    local written = chunk()
    if type(written) ~= "table" or not same_value(written[ROOT_KEY], self.data) then
      error("settings write did not persist")
    end
  end)

  if not ok then
    logger.err("[Ghostwriter] Failed to save settings", tostring(err))
    return false
  end

  return true
end

function GhostwriterSettings:update(patch)
  local previous = {}
  for k, v in pairs(patch or {}) do
    previous[k] = self.data[k]
    self.data[k] = v
  end
  if self:save() then
    return true
  end
  for k in pairs(patch or {}) do
    self.data[k] = previous[k]
  end
  return false
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

function GhostwriterSettings:setConnection(url, token)
  token = tostring(token or ""):gsub("^%s+", ""):gsub("%s+$", "")
  return self:update({ server_url = normalize_server_url(url), api_token = token })
end

-- A missing ledger is an empty ledger. A malformed one must never authorize
-- deletion, and is left untouched so it can be diagnosed instead of adopted.
function GhostwriterSettings:getOwnedDownloads(scope)
  local ledger = self.data.owned_downloads
  if ledger == nil then
    return {}
  end
  if type(ledger) ~= "table" or ledger.version ~= 1 or type(ledger.scopes) ~= "table" then
    return nil
  end
  for key, records in pairs(ledger.scopes) do
    if type(key) ~= "string" or type(records) ~= "table" then
      return nil
    end
    for filename, stamp in pairs(records) do
      if type(filename) ~= "string" or not filename:match("%.epub$")
          or filename:find("[/\\%c]") or type(stamp) ~= "table"
          or type(stamp.size) ~= "number" or type(stamp.modification) ~= "number"
          or type(stamp.ino) ~= "number" or type(stamp.dev) ~= "number"
          or type(stamp.hash) ~= "string" or not stamp.hash:match("^[0-9a-f]+$")
          or #stamp.hash ~= 64
          or stamp.size < 0 or stamp.ino < 0 then
        return nil
      end
    end
  end
  return ledger.scopes[scope] or {}
end

function GhostwriterSettings:hasOwnedDownloads()
  return self.data.owned_downloads ~= nil
end

function GhostwriterSettings:setOwnedDownloads(scope, records)
  if self:getOwnedDownloads(scope) == nil then
    return false
  end
  local old = self.data.owned_downloads
  local scopes = {}
  if old then
    for key, value in pairs(old.scopes) do
      scopes[key] = value
    end
  end
  scopes[scope] = records
  return self:update({ owned_downloads = { version = 1, scopes = scopes } })
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

function GhostwriterSettings:getLastKnownId(scope)
  local cursors = self.data.cursors
  if type(cursors) == "table" and type(cursors[scope]) == "string" then
    return cursors[scope]
  end
  return DEFAULTS.last_known_id
end

function GhostwriterSettings:initializeCursor(scope)
  if self.data.cursors ~= nil or not self.data.last_known_id
      or self.data.last_known_id == "" then
    return true
  end
  -- Preserve the old single cursor for the currently configured connection.
  -- Once saved in a scope, changing server/folder starts with a fresh cursor.
  return self:update({ cursors = { [scope] = tostring(self.data.last_known_id) } })
end

function GhostwriterSettings:setLastKnownId(id, scope)
  local cursors = {}
  if type(self.data.cursors) == "table" then
    for key, value in pairs(self.data.cursors) do cursors[key] = value end
  end
  cursors[scope] = tostring(id or "")
  return self:update({ cursors = cursors })
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
