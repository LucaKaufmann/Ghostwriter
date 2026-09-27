-- Standalone host test: lua ghostwriter/koreader/tests/run.lua
local source = debug.getinfo(1, "S").source:sub(2)
local base = source:gsub("/tests/run.lua$", "/ghostwriter.koplugin")
package.path = base .. "/?.lua;" .. package.path

local function quote(value)
  return "'" .. value:gsub("'", "'\\''") .. "'"
end
local function command_output(command)
  local pipe = assert(io.popen(command, "r"))
  local output = pipe:read("*a")
  local ok = pipe:close()
  if ok then return output end
  return nil
end
local forced_mtime = {}
local function attributes(path)
  local output = command_output("stat -f '%HT|%z|%m|%i|%d' " .. quote(path) .. " 2>/dev/null")
  if not output then return nil end
  local kind, size, mtime, ino, dev = output:match("([^|]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)")
  if not kind then return nil end
  local mode = ({ Directory = "directory", ["Regular File"] = "file", ["Symbolic Link"] = "link" })[kind]
  return { mode = mode, size = tonumber(size), modification = forced_mtime[path] or tonumber(mtime),
    ino = tonumber(ino), dev = tonumber(dev) }
end
package.preload["libs/libkoreader-lfs"] = function() return { symlinkattributes = attributes } end
package.preload.logger = function() return { err = function() end } end
package.preload["ffi/sha2"] = function()
  return { sha256 = function()
    local value = 0
    return function(chunk)
      if not chunk then return string.format("%064x", value) end
      for i = 1, #chunk do value = (value * 257 + chunk:byte(i)) % 4294967296 end
    end
  end }
end
local pending_data = {}
local disk_data = {}
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, child in pairs(value) do result[key] = copy(child) end
  return result
end
local fail_flush = false
local flush_count = 0
local fail_on_flush
package.preload.datastorage = function() return { getSettingsDir = function() return "/private/tmp" end } end
package.preload.luasettings = function()
  return { open = function(_, path)
    return {
      file = path,
      readSetting = function() return copy(disk_data) end,
      saveSetting = function(_, _, value) pending_data = copy(value) end,
      flush = function()
        flush_count = flush_count + 1
        -- Match KOReader: return self even when the disk write silently fails.
        if not fail_flush and flush_count ~= fail_on_flush then disk_data = copy(pending_data) end
        return {}
      end,
    }
  end }
end
local real_loadfile = loadfile
loadfile = function(path)
  if path == "/private/tmp/ghostwriter.lua" then
    return function() return { ghostwriter = copy(disk_data) } end
  end
  return real_loadfile(path)
end
local next_digests = {}
local fail_download = {}
local requested_cursor
package.preload.ghostwriter_api = function()
  return {
    get_new_digests = function(_, _, cursor)
      requested_cursor = cursor
      return true, { digests = next_digests }
    end,
    download_digest = function(_, _, name, target)
      if fail_download[name] then return false end
      local file = assert(io.open(target .. ".part.mock", "wb"))
      file:write("owned:" .. name)
      file:close()
      assert(os.rename(target .. ".part.mock", target))
      return true
    end,
  }
end
local Settings = require("ghostwriter_settings")
local Sync = require("ghostwriter_sync")
local function check(value, message) assert(value, message) end
local function read(path)
  local file = assert(io.open(path, "rb"))
  local contents = file:read("*a")
  file:close()
  return contents
end
local function write(path, contents)
  local file = assert(io.open(path, "wb"))
  file:write(contents)
  file:close()
end
local function digest(id, name)
  return { id = id, filename = name, created_at = id }
end
local tmp = assert(command_output("mktemp -d /private/tmp/ghostwriter-ko-XXXXXX")):gsub("%s+$", "")
local dir = tmp .. "/books"
assert(os.execute("mkdir " .. quote(dir)))
local scope = "https://one.example\n" .. dir .. "\n"
    .. tostring(attributes(dir).dev) .. ":" .. tostring(attributes(dir).ino)
local settings = Settings:new()
check(settings:setConnection("https://one.example/api", "synthetic-token"), "connection")
check(settings:setDownloadDir(dir), "directory")
check(settings:setKeepLastN(1), "retention")
write(dir .. "/personal.epub", "PERSONAL")
next_digests = { digest("1", "one.epub"), digest("2", "two.epub") }
local ok, result = Sync.run(settings)
check(ok and result.downloaded == 2 and result.pruned == 0, "first run pruned without ledger")
next_digests = {}
ok, result = Sync.run(settings)
check(ok and result.pruned == 1, "owned pruning")
check(read(dir .. "/personal.epub") == "PERSONAL", "unrelated book changed")
check(not attributes(dir .. "/one.epub") and attributes(dir .. "/two.epub"), "wrong prune")
local original = read(dir .. "/two.epub")
forced_mtime[dir .. "/two.epub"] = attributes(dir .. "/two.epub").modification
write(dir .. "/two.epub", string.rep("X", #original))
next_digests = { digest("3", "two.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and read(dir .. "/two.epub") == string.rep("X", #original),
  "same-size in-place edit was adopted")
forced_mtime[dir .. "/two.epub"] = nil
next_digests = { digest("3", "three.epub") }
settings.data.owned_downloads = nil
ok, result = Sync.run(settings)
check(ok and result.pruned == 0 and attributes(dir .. "/two.epub"), "missing ledger pruned")
settings.data.owned_downloads = { version = 1, scopes = { malformed = { ["../outside.epub"] = {} } } }
ok = Sync.run(settings)
check(not ok and attributes(dir .. "/two.epub"), "corrupt ledger accepted")
settings.data.owned_downloads = nil
next_digests = { digest("3", "personal.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and read(dir .. "/personal.epub") == "PERSONAL", "collision overwritten")
next_digests = { digest("3", "../outside.epub"), digest("4", "/absolute.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 2 and not attributes(tmp .. "/outside.epub"), "traversal accepted")
next_digests = { digest("3", "retry.epub"), digest("4", "later.epub") }
fail_download["retry.epub"] = true
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and requested_cursor == "3", "failed download cursor")
fail_download["retry.epub"] = nil
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1 and result.skipped_existing == 1 and settings:getLastKnownId(scope) == "4", "contiguous retry")
next_digests = { digest("5", "savefail.epub") }
fail_flush = true
ok, result = Sync.run(settings)
check(ok and result.failed > 0 and not attributes(dir .. "/savefail.epub"), "bookkeeping failure left collision")
fail_flush = false
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1, "bookkeeping retry")
check(settings:getLastKnownId(scope) == "5", "cursor after retry")
next_digests = { digest("6", "cursor.epub") }
fail_on_flush = flush_count + 2
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1 and settings:getLastKnownId(scope) == "5", "cursor save failure advanced")
fail_on_flush = nil
ok, result = Sync.run(settings)
check(ok and result.skipped_existing == 1 and settings:getLastKnownId(scope) == "6", "cursor retry")
check(settings:setKeepLastN(0), "zero retention setting")
next_digests = { digest("7", "six.epub") }
ok, result = Sync.run(settings)
check(ok and result.pruned == 0 and attributes(dir .. "/savefail.epub"), "zero retention pruned")
write(tmp .. "/outside.epub", "OUTSIDE")
assert(os.execute("ln -s " .. quote(tmp .. "/outside.epub") .. " " .. quote(dir .. "/linked.epub")))
next_digests = { digest("8", "linked.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and read(tmp .. "/outside.epub") == "OUTSIDE", "symlink target changed")
write(dir .. "/stale.epub.part", "PART")
next_digests = { digest("8", "stale.epub") }
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1 and read(dir .. "/stale.epub.part") == "PART", "partial retry failed")
check(settings:setConnection("https://two.example", "synthetic-token"), "new server")
next_digests = {}
ok, result = Sync.run(settings)
check(ok and requested_cursor == "" and result.pruned == 0, "server scope leaked")
check(settings:setDownloadDir(tmp), "new directory")
ok, result = Sync.run(settings)
check(ok and requested_cursor == "" and result.pruned == 0, "directory scope leaked")
assert(os.execute("ln -s " .. quote(dir) .. " " .. quote(tmp .. "/link")))
check(settings:setDownloadDir(tmp .. "/link"), "symlink setting")
ok = Sync.run(settings)
check(not ok, "symlink directory accepted")
check(settings:setDownloadDir(dir), "restore directory")
check(settings:setConnection("https://legacy.example", "synthetic-token"), "legacy connection")
settings.data.cursors = nil
settings.data.last_known_id = "legacy-id"
next_digests = {}
ok = Sync.run(settings)
check(ok and requested_cursor == "legacy-id", "legacy cursor lost")
check(settings:setConnection("https://another.example", "synthetic-token"), "switch legacy server")
ok = Sync.run(settings)
check(ok and requested_cursor == "", "legacy cursor leaked to new server")

-- Exercise the actual dialog callbacks; Lua scoping is the regression here.
local shown, closed
local dialog_values = { "https://dialog.example/api", "dialog-token" }
package.preload.gettext = function() return function(value) return value end end
package.preload.dispatcher = function() return { registerAction = function() end } end
package.preload["ui/widget/infomessage"] = function()
  return { new = function(_, spec) return spec end }
end
package.preload["ui/widget/multiinputdialog"] = function()
  return { new = function(_, spec)
    spec.getFields = function() return dialog_values end
    spec.onShowKeyboard = function() end
    return spec
  end }
end
package.preload["ui/widget/spinwidget"] = function() return {} end
package.preload["ui/uimanager"] = function()
  return { show = function(_, widget) shown = widget end,
           close = function(_, widget) closed = widget end }
end
package.preload["ui/widget/container/widgetcontainer"] = function()
  return { extend = function(_, object) return object end }
end
local plugin = require("main")
plugin.settings = settings
plugin:editConnectionSettings()
local dialog = shown
dialog.buttons[1][1].callback()
check(closed == dialog, "cancel did not close current dialog")
plugin:editConnectionSettings()
dialog = shown
closed = nil
dialog.buttons[1][2].callback()
check(closed == dialog and settings:getServerURL() == "https://dialog.example"
    and settings:getApiToken() == "dialog-token", "save did not use current dialog")
plugin:editConnectionSettings()
dialog = shown
closed = nil
fail_flush = true
dialog_values = { "https://unsaved.example", "unsaved-token" }
dialog.buttons[1][2].callback()
check(closed == nil and settings:getServerURL() == "https://dialog.example", "failed save closed dialog")
fail_flush = false

-- Run the real transport finalization with LuaJIT FFI and a fake HTTP server.
-- The server creates a racing destination after the request begins.
if pcall(require, "ffi") then
  local race_target
  package.preload.json = function() return { decode = function() return {} end } end
  package.preload.ltn12 = function() return { sink = { table = function() return function() end end } } end
  package.preload.socket = function()
    return { skip = function(n, ...) return select(n + 1, ...) end }
  end
  package.preload.socketutil = function()
    return { set_timeout = function() end, reset_timeout = function() end }
  end
  package.preload["socket.url"] = function() return { escape = function(value) return value end } end
  package.preload["socket.http"] = function()
    return { request = function(request)
      request.sink("network-content")
      if race_target then write(race_target, "PERSONAL RACE") end
      return 1, 200, {}, "OK"
    end }
  end
  local real_api = dofile(base .. "/ghostwriter_api.lua")
  local target = dir .. "/transport.epub"
  write(target .. ".part", "OLD PART")
  local dl_ok = real_api.download_digest("https://test.example", "synthetic", "transport.epub", target)
  check(dl_ok and read(target) == "network-content" and read(target .. ".part") == "OLD PART",
    "real transport failed exclusive partial retry")
  race_target = dir .. "/race.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "race.epub", race_target)
  check(not dl_ok and read(race_target) == "PERSONAL RACE", "real transport overwrote racing book")
end
assert(os.execute("rm -rf " .. quote(tmp)))
print("KO-01 host Lua checks passed")
