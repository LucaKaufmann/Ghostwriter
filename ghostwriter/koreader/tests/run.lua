-- Standalone host test: luajit ghostwriter/koreader/tests/run.lua
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
local primary_corrupt = false
local primary_file_present = false
local function attributes(path, follow)
  if path == "/private/tmp/ghostwriter.lua" and (primary_corrupt or primary_file_present) then
    return { mode = "file" }
  end
  local output = command_output("stat " .. (follow and "-L " or "")
      .. "-f '%HT|%z|%m|%i|%d' " .. quote(path) .. " 2>/dev/null")
  if not output then return nil end
  local kind, size, mtime, ino, dev = output:match("([^|]+)|([^|]+)|([^|]+)|([^|]+)|([^|]+)")
  if not kind then return nil end
  local mode = ({ Directory = "directory", ["Regular File"] = "file", ["Symbolic Link"] = "link" })[kind]
  return { mode = mode, size = tonumber(size), modification = forced_mtime[path] or tonumber(mtime),
    ino = tonumber(ino), dev = tonumber(dev) }
end
package.preload["libs/libkoreader-lfs"] = function()
  return { symlinkattributes = attributes, attributes = function(path) return attributes(path, true) end }
end
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
local backup_data = {}
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, child in pairs(value) do result[key] = copy(child) end
  return result
end
local fail_flush = false
local flush_count = 0
local fail_on_flush
local after_flush
package.preload.datastorage = function() return { getSettingsDir = function() return "/private/tmp" end } end
package.preload.luasettings = function()
  return { open = function(_, path)
    return {
      file = path,
      readSetting = function()
        return copy((primary_corrupt or not primary_file_present) and backup_data or disk_data)
      end,
      saveSetting = function(_, _, value) pending_data = copy(value) end,
      flush = function()
        flush_count = flush_count + 1
        -- Match KOReader: return self even when the disk write silently fails.
        if not fail_flush and flush_count ~= fail_on_flush then
          disk_data = copy(pending_data)
          primary_file_present = true
        end
        if after_flush then after_flush() end
        return {}
      end,
    }
  end }
end
local real_loadfile = loadfile
loadfile = function(path)
  if path == "/private/tmp/ghostwriter.lua" then
    if primary_corrupt or not primary_file_present then return nil, "missing or corrupt primary" end
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
      return true, { created = attributes(target) }
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
check(ok and result.pruned == 0 and attributes(dir .. "/six.epub"), "zero retention pruned")
write(tmp .. "/outside.epub", "OUTSIDE")
assert(os.execute("ln -s " .. quote(tmp .. "/outside.epub") .. " " .. quote(dir .. "/linked.epub")))
next_digests = { digest("8", "linked.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and read(tmp .. "/outside.epub") == "OUTSIDE", "symlink target changed")
write(dir .. "/stale.epub.part", "PART")
next_digests = { digest("8", "stale.epub") }
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1 and read(dir .. "/stale.epub.part") == "PART", "partial retry failed")
local real_open = io.open
io.open = function(path, mode)
  if path == dir .. "/stampfail.epub" and mode == "rb" then return nil, "injected read failure" end
  return real_open(path, mode)
end
next_digests = { digest("9", "stampfail.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and not attributes(dir .. "/stampfail.epub"),
  "unrecorded finalized file blocked retry")
io.open = real_open
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1, "stamp failure retry")
local read_count = 0
io.open = function(path, mode)
  if path == dir .. "/readerror.epub" and mode == "rb" then
    return { read = function()
      read_count = read_count + 1
      if read_count == 1 then return "prefix" end
      return nil, "injected I/O error"
    end, close = function() end }
  end
  return real_open(path, mode)
end
next_digests = { digest("10", "readerror.epub") }
ok, result = Sync.run(settings)
check(ok and result.failed == 1 and not attributes(dir .. "/readerror.epub"),
  "mid-file hash read error blocked retry")
io.open = real_open
ok, result = Sync.run(settings)
check(ok and result.downloaded == 1, "read error retry")
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
backup_data = copy(disk_data)
primary_corrupt = true
local recovered = Settings:new()
check(recovered.data.owned_downloads == nil and recovered.data.cursors == nil,
  "corrupt primary adopted backup ownership")
next_digests = {}
ok, result = Sync.run(recovered)
check(ok and result.pruned == 0 and read(dir .. "/personal.epub") == "PERSONAL",
  "corrupt primary enabled pruning")
primary_corrupt = false
primary_file_present = false
local missing_primary = Settings:new()
check(missing_primary.data.owned_downloads == nil and missing_primary.data.cursors == nil,
  "missing primary adopted backup ownership")
ok, result = Sync.run(missing_primary)
check(ok and result.pruned == 0, "missing primary enabled pruning")
primary_file_present = true

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

local prune_dir = tmp .. "/prune-race"
assert(os.execute("mkdir " .. quote(prune_dir)))
check(settings:setDownloadDir(prune_dir) and settings:setKeepLastN(0), "prune fixture settings")
forced_mtime[prune_dir .. "/a.epub"] = 100
forced_mtime[prune_dir .. "/z.epub"] = 100
next_digests = { digest("10", "a.epub"), digest("11", "z.epub") }
ok, result = Sync.run(settings)
check(ok and result.downloaded == 2, "prune fixture downloads")
check(settings:setKeepLastN(1), "enable prune fixture")
next_digests = {}
after_flush = function()
  after_flush = nil
  write(prune_dir .. "/a.epub", string.rep("Y", #read(prune_dir .. "/a.epub")))
end
ok, result = Sync.run(settings)
check(ok and result.pruned == 0 and read(prune_dir .. "/a.epub") == string.rep("Y", 12)
    and attributes(prune_dir .. "/z.epub"), "prune deleted book changed during settings save")
after_flush = nil

-- Run the real transport finalization with LuaJIT FFI and a fake HTTP server.
-- The server creates a racing destination after the request begins.
if pcall(require, "ffi") then
  local race_target
  local during_request
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
      if during_request then during_request() end
      return 1, 200, {}, "OK"
    end }
  end
  local real_api = dofile(base .. "/ghostwriter_api.lua")
  local target = dir .. "/transport.epub"
  write(target .. ".part", "OLD PART")
  local dl_ok, dl_info = real_api.download_digest("https://test.example", "synthetic", "transport.epub", target, attributes(dir))
  check(dl_ok and read(target) == "network-content" and read(target .. ".part") == "OLD PART",
    "real transport failed exclusive partial retry")
  race_target = dir .. "/race.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "race.epub", race_target, attributes(dir))
  check(not dl_ok and read(race_target) == "PERSONAL RACE", "real transport overwrote racing book")
  race_target = nil
  local ffi = require("ffi")
  local function unsupported()
    ffi.errno(95)
    return -1
  end
  local fallback = { renameat2 = unsupported, linkat = unsupported }
  local copy_target = dir .. "/copy.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "copy.epub",
    copy_target, attributes(dir), fallback)
  check(dl_ok and read(copy_target) == "network-content", "exclusive copy fallback failed")
  race_target = dir .. "/copy-race.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "copy-race.epub",
    race_target, attributes(dir), fallback)
  check(not dl_ok and read(race_target) == "PERSONAL RACE", "fallback overwrote racing book")
  race_target = nil
  local target_fd
  local short_written = false
  local copy_fault = {
    renameat2 = unsupported,
    linkat = unsupported,
    openat = function(dirfd, name, flags, mode)
      local fd = ffi.C.openat(dirfd, name, flags, mode)
      if name == "short.epub" or name == "fsync.epub" then target_fd = fd end
      return fd
    end,
    write = function(fd, buffer, count)
      if fd == target_fd then
        if not short_written then
          short_written = true
          return ffi.C.write(fd, buffer, 3)
        end
        ffi.errno(28)
        return -1
      end
      return ffi.C.write(fd, buffer, count)
    end,
  }
  local short_target = dir .. "/short.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "short.epub",
    short_target, attributes(dir), copy_fault)
  check(not dl_ok and not attributes(short_target), "failed fallback copy left target")
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "short.epub",
    short_target, attributes(dir), fallback)
  check(dl_ok and read(short_target) == "network-content", "failed copy retry")
  target_fd = nil
  copy_fault.write = nil
  copy_fault.fsync = function(fd)
    if fd == target_fd then ffi.errno(28); return -1 end
    return ffi.C.fsync(fd)
  end
  local fsync_target = dir .. "/fsync.epub"
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "fsync.epub",
    fsync_target, attributes(dir), copy_fault)
  check(not dl_ok and not attributes(fsync_target), "failed fallback fsync left target")
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "fsync.epub",
    fsync_target, attributes(dir), fallback)
  check(dl_ok and read(fsync_target) == "network-content", "failed fsync retry")
  target_fd = nil
  copy_fault.fsync = nil
  local replacement_target = dir .. "/replacement.epub"
  copy_fault.openat = function(dirfd, name, flags, mode)
    local fd = ffi.C.openat(dirfd, name, flags, mode)
    if name == "replacement.epub" then target_fd = fd end
    return fd
  end
  copy_fault.write = function(fd, buffer, count)
    if fd == target_fd then
      assert(os.remove(replacement_target))
      write(replacement_target, "PERSONAL REPLACEMENT")
      ffi.errno(28)
      return -1
    end
    return ffi.C.write(fd, buffer, count)
  end
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "replacement.epub",
    replacement_target, attributes(dir), copy_fault)
  check(not dl_ok and read(replacement_target) == "PERSONAL REPLACEMENT",
    "failed fallback cleanup deleted replacement")
  check(settings:setDownloadDir(dir) and settings:setConnection("https://test.example", "synthetic")
      and settings:setKeepLastN(0), "integration fixture settings")
  package.loaded.ghostwriter_api = {
    get_new_digests = function() return true, { digests = { digest("12", "integrated.epub") } } end,
    download_digest = real_api.download_digest,
  }
  package.loaded.ghostwriter_sync = nil
  local integrated_sync = require("ghostwriter_sync")
  fail_flush = true
  ok, result = integrated_sync.run(settings)
  check(ok and result.failed == 1 and not attributes(dir .. "/integrated.epub"),
    "real API failed-save cleanup left unowned final file")
  fail_flush = false
  ok, result = integrated_sync.run(settings)
  check(ok and result.downloaded == 1 and attributes(dir .. "/integrated.epub"),
    "real API failed-save retry")
  local moved = dir .. "-moved"
  local outside_dir = tmp .. "/other-books"
  assert(os.execute("mkdir " .. quote(outside_dir)))
  during_request = function()
    assert(os.rename(dir, moved))
    assert(os.execute("ln -s " .. quote(outside_dir) .. " " .. quote(dir)))
  end
  dl_ok = real_api.download_digest("https://test.example", "synthetic", "swapped.epub",
    dir .. "/swapped.epub", attributes(dir))
  check(not dl_ok and not attributes(outside_dir .. "/swapped.epub")
    and not attributes(moved .. "/swapped.epub"), "directory swap escaped destination")
  during_request = nil
  assert(os.remove(dir))
  assert(os.rename(moved, dir))
end
assert(os.execute("rm -rf " .. quote(tmp)))
print("KO-01 host Lua checks passed")
