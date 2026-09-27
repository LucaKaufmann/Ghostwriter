local api = require("ghostwriter_api")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

local GhostwriterSync = {}

local function join_path(dir, filename)
  return dir .. "/" .. filename
end

local function safe_filename(name)
  return type(name) == "string" and name ~= "" and name:match("%.epub$")
      and not name:find("[/\\%c]") and name ~= "." and name ~= ".."
end

local function safe_directory(path)
  if type(path) ~= "string" or path:sub(1, 1) ~= "/" or path:find("%c") then
    return nil
  end
  local parts = {}
  for part in path:gmatch("[^/]+") do
    if part == ".." or part == "." then
      return nil
    end
    table.insert(parts, part)
  end
  local current = ""
  for _, part in ipairs(parts) do
    current = current .. "/" .. part
    local attr = lfs.symlinkattributes(current)
    if not attr or attr.mode == "link" or attr.mode ~= "directory" then
      return nil
    end
  end
  return current == "" and "/" or current
end

local function ownership_scope(server_url, download_dir)
  local attr = lfs.symlinkattributes(download_dir)
  if not attr or type(attr.dev) ~= "number" or type(attr.ino) ~= "number" then
    return nil
  end
  return server_url .. "\n" .. download_dir .. "\n" .. tostring(attr.dev) .. ":" .. tostring(attr.ino)
end

local function regular_file(path)
  local attr = lfs.symlinkattributes(path)
  if attr and attr.mode == "file" then
    return attr
  end
  return nil
end

local function same_file(attr, stamp)
  return attr and attr.size == stamp.size and attr.modification == stamp.modification
      and attr.ino == stamp.ino and attr.dev == stamp.dev
end

local function stamp_for(attr)
  if not attr or type(attr.size) ~= "number" or type(attr.modification) ~= "number"
      or type(attr.ino) ~= "number" or type(attr.dev) ~= "number" then
    return nil
  end
  return { size = attr.size, modification = attr.modification, ino = attr.ino, dev = attr.dev }
end

local function copy_records(records)
  local result = {}
  for name, stamp in pairs(records) do
    result[name] = stamp
  end
  return result
end

local function sort_oldest_first(digests)
  table.sort(digests, function(a, b)
    return tostring(a.created_at or "") < tostring(b.created_at or "")
  end)
end

local function prune_owned(settings, server_url, scope, download_dir, keep_last_n)
  if keep_last_n <= 0 then
    return 0
  end
  local records = settings:getOwnedDownloads(scope)
  if not records then
    return 0
  end
  local files = {}
  for name, stamp in pairs(records) do
    if not safe_filename(name) then
      return 0
    end
    local path = join_path(download_dir, name)
    local attr = regular_file(path)
    if same_file(attr, stamp) then
      table.insert(files, { name = name, path = path, mtime = attr.modification })
    end
  end
  table.sort(files, function(a, b)
    if a.mtime == b.mtime then
      return a.name > b.name
    end
    return a.mtime > b.mtime
  end)
  local removed = 0
  for i = keep_last_n + 1, #files do
    local file = files[i]
    local fresh_dir = safe_directory(download_dir)
    if fresh_dir ~= download_dir or ownership_scope(server_url, download_dir) ~= scope
        or not same_file(regular_file(file.path), records[file.name]) then
      break
    end
    -- Forget ownership durably first. A failed unlink leaves the book intact.
    local next_records = copy_records(records)
    next_records[file.name] = nil
    if not settings:setOwnedDownloads(scope, next_records) then
      break
    end
    records = next_records
    if os.remove(file.path) then
      removed = removed + 1
    end
  end
  return removed
end

function GhostwriterSync.run(settings, progress_cb)
  local server_url = settings:getServerURL()
  local api_token = settings:getApiToken()
  local download_dir = safe_directory(settings:getDownloadDir())
  if server_url == "" then
    return false, "Server URL is not configured"
  end
  if api_token == "" then
    return false, "API token is not configured"
  end
  if not download_dir then
    return false, "Download folder is unsafe or does not exist"
  end
  local scope = ownership_scope(server_url, download_dir)
  if not scope then
    return false, "Download folder identity is unavailable"
  end
  local had_ownership_state = settings:hasOwnedDownloads()
  local can_prune = had_ownership_state
  local records = settings:getOwnedDownloads(scope)
  if not records then
    return false, "Download ownership state is invalid"
  end
  for name in pairs(records) do
    if not safe_filename(name) then
      return false, "Download ownership state is invalid"
    end
  end
  if not settings:initializeCursor(scope) then
    return false, "Failed to save download cursor"
  end
  if progress_cb then
    progress_cb({ phase = "query" })
  end
  local ok, response = api.get_new_digests(server_url, api_token, settings:getLastKnownId(scope))
  if not ok then
    if response and response.code == 401 then
      return false, "Authentication failed (401)"
    end
    return false, "Failed to check for new digests"
  end
  local digests = response.digests or {}
  sort_oldest_first(digests)
  local downloaded, skipped_existing, failed, pruned = 0, 0, 0, 0
  local newest_contiguous_success_id = nil
  local can_advance_cursor = true
  for idx, digest in ipairs(digests) do
    local filename, digest_id = digest.filename, digest.id
    if progress_cb then
      progress_cb({ phase = "download", current = idx, total = #digests, filename = filename })
    end
    if not safe_filename(filename) or not digest_id then
      failed = failed + 1
      can_advance_cursor = false
    else
      local target_path = join_path(download_dir, filename)
      local target_attr = lfs.symlinkattributes(target_path)
      local part_attr = lfs.symlinkattributes(target_path .. ".part")
      if safe_directory(download_dir) ~= download_dir
          or ownership_scope(server_url, download_dir) ~= scope then
        failed = failed + 1
        can_advance_cursor = false
      elseif target_attr then
        -- An existing file is never adopted. It can satisfy the cursor only
        -- when it is still the exact file previously recorded by this plugin.
        if same_file(regular_file(target_path), records[filename] or {}) then
          skipped_existing = skipped_existing + 1
          if can_advance_cursor then newest_contiguous_success_id = digest_id end
        else
          failed = failed + 1
          can_advance_cursor = false
        end
      elseif part_attr then
        failed = failed + 1
        can_advance_cursor = false
      else
        local dl_ok = api.download_digest(server_url, api_token, filename, target_path)
        local stamp = stamp_for(regular_file(target_path))
        if dl_ok and stamp and safe_directory(download_dir) == download_dir
            and ownership_scope(server_url, download_dir) == scope then
          local next_records = copy_records(records)
          next_records[filename] = stamp
          if settings:setOwnedDownloads(scope, next_records) then
            records = next_records
            downloaded = downloaded + 1
            if can_advance_cursor then newest_contiguous_success_id = digest_id end
          else
            -- A finalized but unrecorded file must not become a collision on
            -- retry. Remove only the file just created, after rechecking it.
            if safe_directory(download_dir) == download_dir
                and ownership_scope(server_url, download_dir) == scope
                and same_file(regular_file(target_path), stamp) then
              os.remove(target_path)
            end
            failed = failed + 1
            can_advance_cursor = false
          end
        else
          failed = failed + 1
          can_advance_cursor = false
          logger.err("[Ghostwriter] Failed to download digest", tostring(filename))
        end
      end
    end
  end
  if newest_contiguous_success_id and newest_contiguous_success_id ~= "" then
    if not settings:setLastKnownId(newest_contiguous_success_id, scope) then
      failed = failed + 1
      can_prune = false
    end
  end
  if can_prune then
    pruned = prune_owned(settings, server_url, scope, download_dir, settings:getKeepLastN())
  end
  return true, {
    downloaded = downloaded,
    skipped_existing = skipped_existing,
    failed = failed,
    pruned = pruned,
    message = #digests == 0 and "No new digests" or "Sync complete",
  }
end

return GhostwriterSync
