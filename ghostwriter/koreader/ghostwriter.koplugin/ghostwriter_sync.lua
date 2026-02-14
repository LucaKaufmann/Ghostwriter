local api = require("ghostwriter_api")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

local GhostwriterSync = {}

local function join_path(dir, filename)
  if dir:sub(-1) == "/" then
    return dir .. filename
  end
  return dir .. "/" .. filename
end

local function file_exists(path)
  local fh = io.open(path, "rb")
  if fh then
    fh:close()
    return true
  end
  return false
end

local function is_directory(path)
  return lfs.attributes(path, "mode") == "directory"
end

local function sort_oldest_first(digests)
  table.sort(digests, function(a, b)
    local a_time = tostring(a.created_at or "")
    local b_time = tostring(b.created_at or "")
    return a_time < b_time
  end)
end

local function prune_old_epubs(download_dir, keep_last_n)
  if keep_last_n <= 0 then
    return 0
  end

  local files = {}
  for entry in lfs.dir(download_dir) do
    if entry ~= "." and entry ~= ".." and entry:match("%.epub$") then
      local full_path = join_path(download_dir, entry)
      local mode = lfs.attributes(full_path, "mode")
      if mode == "file" then
        local mtime = lfs.attributes(full_path, "modification") or 0
        table.insert(files, { name = entry, path = full_path, mtime = mtime })
      end
    end
  end

  if #files <= keep_last_n then
    return 0
  end

  table.sort(files, function(a, b)
    return a.mtime > b.mtime
  end)

  local removed = 0
  for i = keep_last_n + 1, #files do
    local ok = os.remove(files[i].path)
    if ok then
      removed = removed + 1
    end
  end

  return removed
end

function GhostwriterSync.run(settings, progress_cb)
  local server_url = settings:getServerURL()
  local api_token = settings:getApiToken()
  local download_dir = settings:getDownloadDir()

  if server_url == "" then
    return false, "Server URL is not configured"
  end

  if api_token == "" then
    return false, "API token is not configured"
  end

  if download_dir == "" then
    return false, "Download folder is not configured"
  end

  if not is_directory(download_dir) then
    return false, "Download folder does not exist"
  end

  local last_known_id = settings:getLastKnownId()

  if progress_cb then
    progress_cb({ phase = "query" })
  end

  local ok, response = api.get_new_digests(server_url, api_token, last_known_id)
  if not ok then
    local code = response and response.code
    if code == 401 then
      return false, "Authentication failed (401)"
    end
    return false, "Failed to check for new digests"
  end

  local digests = response.digests or {}
  if #digests == 0 then
    return true, {
      downloaded = 0,
      skipped_existing = 0,
      failed = 0,
      pruned = 0,
      message = "No new digests",
    }
  end

  sort_oldest_first(digests)

  local downloaded = 0
  local skipped_existing = 0
  local failed = 0
  local newest_contiguous_success_id = nil
  local can_advance_cursor = true

  for idx, digest in ipairs(digests) do
    local filename = digest.filename
    local digest_id = digest.id

    if progress_cb then
      progress_cb({
        phase = "download",
        current = idx,
        total = #digests,
        filename = filename,
      })
    end

    local target_path = join_path(download_dir, filename)

    if file_exists(target_path) then
      skipped_existing = skipped_existing + 1
      if can_advance_cursor then
        newest_contiguous_success_id = digest_id
      end
    else
      local dl_ok = api.download_digest(server_url, api_token, filename, target_path)
      if dl_ok then
        downloaded = downloaded + 1
        if can_advance_cursor then
          newest_contiguous_success_id = digest_id
        end
      else
        failed = failed + 1
        can_advance_cursor = false
        logger.err("[Ghostwriter] Failed to download digest", tostring(filename))
      end
    end
  end

  if newest_contiguous_success_id and newest_contiguous_success_id ~= "" then
    settings:setLastKnownId(newest_contiguous_success_id)
  end

  local keep_last_n = settings:getKeepLastN()
  local pruned = prune_old_epubs(download_dir, keep_last_n)

  return true, {
    downloaded = downloaded,
    skipped_existing = skipped_existing,
    failed = failed,
    pruned = pruned,
    message = "Sync complete",
  }
end

return GhostwriterSync
