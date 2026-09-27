local api = require("ghostwriter_api")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local sha256 = require("ffi/sha2").sha256

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

local function file_hash(path)
  local file = io.open(path, "rb")
  if not file then return nil end
  local update = sha256()
  while true do
    local chunk, read_err = file:read(65536)
    if not chunk then
      file:close()
      if read_err then return nil end
      break
    end
    update(chunk)
  end
  return update()
end

local function same_file(path, attr, stamp)
  return attr and attr.size == stamp.size and attr.modification == stamp.modification
      and attr.ino == stamp.ino and attr.dev == stamp.dev
      and file_hash(path) == stamp.hash
end

local function stamp_for(path, attr)
  if not attr or type(attr.size) ~= "number" or type(attr.modification) ~= "number"
      or type(attr.ino) ~= "number" or type(attr.dev) ~= "number" then
    return nil
  end
  local hash = file_hash(path)
  if not hash then return nil end
  return { size = attr.size, modification = attr.modification, ino = attr.ino,
    dev = attr.dev, hash = hash }
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
    if same_file(path, attr, stamp) then
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
    local stamp = records[file.name]
    local fresh_dir = safe_directory(download_dir)
    if fresh_dir ~= download_dir or ownership_scope(server_url, download_dir) ~= scope
        or not same_file(file.path, regular_file(file.path), stamp) then
      break
    end
    -- Forget ownership durably first. A failed unlink leaves the book intact.
    local next_records = copy_records(records)
    next_records[file.name] = nil
    if not settings:setOwnedDownloads(scope, next_records) then
      break
    end
    records = next_records
    if safe_directory(download_dir) == download_dir
        and ownership_scope(server_url, download_dir) == scope
        and same_file(file.path, regular_file(file.path), stamp) and os.remove(file.path) then
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
      if safe_directory(download_dir) ~= download_dir
          or ownership_scope(server_url, download_dir) ~= scope then
        failed = failed + 1
        can_advance_cursor = false
      elseif target_attr then
        -- An existing file is never adopted. It can satisfy the cursor only
        -- when it is still the exact file previously recorded by this plugin.
        if same_file(target_path, regular_file(target_path), records[filename] or {}) then
          skipped_existing = skipped_existing + 1
          if can_advance_cursor then newest_contiguous_success_id = digest_id end
        else
          failed = failed + 1
          can_advance_cursor = false
        end
      else
        local dl_ok, dl_info = api.download_digest(server_url, api_token, filename,
          target_path, lfs.symlinkattributes(download_dir))
        local stamp = stamp_for(target_path, regular_file(target_path))
        local function cleanup_created()
          local current = regular_file(target_path)
          local created = dl_info and dl_info.created
          if created and current and current.dev == created.dev and current.ino == created.ino
              and safe_directory(download_dir) == download_dir
              and ownership_scope(server_url, download_dir) == scope then
            -- A content check is available after stamping; use it when the
            -- failure followed a slow settings write.
            -- A failed read is not evidence that the file is still ours.
            if dl_info.hash and file_hash(target_path) == dl_info.hash
                and (not stamp or same_file(target_path, current, stamp)) then
              os.remove(target_path)
            end
          end
        end
        -- Never adopt a replacement that appeared after finalization.
        local created = dl_info and dl_info.created
        if dl_ok and stamp and created
            and stamp.dev == created.dev and stamp.ino == created.ino
            and stamp.hash == dl_info.hash
            and safe_directory(download_dir) == download_dir
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
            cleanup_created()
            failed = failed + 1
            can_advance_cursor = false
          end
        else
          if dl_ok then cleanup_created() end
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
