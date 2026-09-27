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
local function attributes(path)
  local output = command_output("stat -f '%HT|%z|%m|%i|%d' " .. quote(path) .. " 2>/dev/null")
  if not output then return nil end
  local kind, size, mtime, ino, dev = output:match("([^|]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)")
  local mode = ({ Directory = "directory", ["Regular File"] = "file", ["Symbolic Link"] = "link" })[kind]
  return { mode = mode, size = tonumber(size), modification = tonumber(mtime), ino = tonumber(ino), dev = tonumber(dev) }
end
package.preload["libs/libkoreader-lfs"] = function() return { symlinkattributes = attributes } end
package.preload.logger = function() return { err = function() end } end
local settings_data = {}
local fail_flush = false
local flush_count = 0
local fail_on_flush
package.preload.datastorage = function() return { getSettingsDir = function() return "/private/tmp" end } end
package.preload.luasettings = function()
  return { open = function()
    return {
      readSetting = function() return settings_data end,
      saveSetting = function(_, _, value) settings_data = value end,
      flush = function()
        flush_count = flush_count + 1
        if fail_flush or flush_count == fail_on_flush then return false end
        return true
      end,
    }
  end }
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
      local file = assert(io.open(target .. ".part", "wb"))
      file:write("owned:" .. name)
      file:close()
      assert(os.rename(target .. ".part", target))
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
write(dir .. "/two.epub", "REPLACED BY USER")
next_digests = { digest("3", "two.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and read(dir .. "/two.epub") == "REPLACED BY USER", "replaced owned file changed")
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
check(ok and result.failed == 1 and read(dir .. "/stale.epub.part") == "PART", "partial collision changed")
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
package.preload.gettext = function() return function(value) return value end end
package.preload.dispatcher = function() return { registerAction = function() end } end
package.preload["ui/widget/infomessage"] = function()
  return { new = function(_, spec) return spec end }
end
package.preload["ui/widget/multiinputdialog"] = function()
  return { new = function(_, spec)
    spec.getFields = function() return { "https://dialog.example/api", "dialog-token" } end
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
dialog.buttons[1][2].callback()
check(closed == nil and settings:getServerURL() == "https://dialog.example", "failed save closed dialog")
fail_flush = false
assert(os.execute("rm -rf " .. quote(tmp)))
print("KO-01 host Lua checks passed")
