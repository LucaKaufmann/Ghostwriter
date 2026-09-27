local JSON = require("json")
local logger = require("logger")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")
local http = require("socket.http")
local url = require("socket.url")
local lfs = require("libs/libkoreader-lfs")
local ffi = require("ffi")

ffi.cdef([[
  int open(const char *path, int flags, ...);
  int openat(int dirfd, const char *path, int flags, ...);
  long read(int fd, void *buf, unsigned long count);
  long write(int fd, const void *buf, unsigned long count);
  int fsync(int fd);
  int close(int fd);
  int linkat(int olddirfd, const char *oldpath, int newdirfd, const char *newpath, int flags);
  int unlinkat(int dirfd, const char *path, int flags);
  int renameat2(int olddirfd, const char *oldpath, int newdirfd, const char *newpath, unsigned int flags);
  int getpid(void);
]])

local API = {}

local function join_url(base, path)
  if base:sub(-1) == "/" then
    base = base:sub(1, -2)
  end
  if path:sub(1, 1) ~= "/" then
    path = "/" .. path
  end
  return base .. path
end

local function with_query(url_str, params)
  if not params then
    return url_str
  end

  local parts = {}
  for key, value in pairs(params) do
    if value ~= nil and value ~= "" then
      table.insert(parts, url.escape(tostring(key)) .. "=" .. url.escape(tostring(value)))
    end
  end

  if #parts == 0 then
    return url_str
  end

  return url_str .. "?" .. table.concat(parts, "&")
end

local function auth_headers(token)
  local headers = {
    ["Accept"] = "application/json",
  }

  if token and token ~= "" then
    headers["Authorization"] = "Bearer " .. token
  end

  return headers
end

function API.get_json(url_str, token)
  local sink = {}
  local request = {
    url = url_str,
    method = "GET",
    headers = auth_headers(token),
    sink = ltn12.sink.table(sink),
  }

  socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
  local code, resp_headers, status = socket.skip(1, http.request(request))
  socketutil:reset_timeout()

  if resp_headers == nil then
    return false, { kind = "network_error", code = code, status = status }
  end

  local body = table.concat(sink or {})

  if code >= 200 and code < 300 then
    if body == nil or body == "" then
      return true, {}
    end

    local ok, decoded = pcall(JSON.decode, body)
    if ok and decoded then
      return true, decoded
    end

    logger.err("[Ghostwriter] Invalid JSON response", tostring(body))
    return false, { kind = "invalid_json", code = code, body = body }
  end

  return false, {
    kind = "http_error",
    code = code,
    status = status,
    body = body,
  }
end

function API.get_new_digests(server_url, token, last_known_id)
  local endpoint = join_url(server_url, "/api/digests/new")
  local req_url = with_query(endpoint, { last_known_id = last_known_id })
  return API.get_json(req_url, token)
end

local part_counter = 0

local function fd_attributes(fd)
  local base = ffi.os == "OSX" and "/dev/fd/" or "/proc/self/fd/"
  return lfs.attributes(base .. tostring(fd))
end

local function same_identity(a, b)
  return a and b and a.mode == "directory" and b.mode == "directory"
      and a.dev == b.dev and a.ino == b.ino
end

local function same_open_identity(a, b)
  -- macOS /dev/fd reports the fdesc device number for an open descriptor.
  return a and b and a.mode == b.mode and a.ino == b.ino
      and (ffi.os == "OSX" or a.dev == b.dev)
end

function API.download_digest(server_url, token, filename, target_path, expected_dir, filesystem_ops)
  if type(filename) ~= "string" or not filename:match("%.epub$")
      or filename:find("[/\\%c]") or type(expected_dir) ~= "table" then
    return false, { kind = "unsafe_path" }
  end
  local dir = target_path:match("^(.*)/[^/]+$")
  if not dir or target_path ~= dir .. "/" .. filename then
    return false, { kind = "unsafe_path" }
  end
  local function call(name, ...)
    local function_op = filesystem_ops and filesystem_ops[name]
    if function_op then return function_op(...) end
    return ffi.C[name](...)
  end
  local create_flags = ffi.os == "OSX" and 0x0A01 or 0x00C1 -- WRONLY|CREAT|EXCL
  local dirfd = call("open", dir, 0)
  if dirfd < 0 then return false, { kind = "unsafe_path" } end
  local function dir_matches()
    return same_open_identity(fd_attributes(dirfd), expected_dir)
        and same_identity(lfs.symlinkattributes(dir), expected_dir)
  end
  local function finalized_identity(open_identity)
    local current = lfs.symlinkattributes(target_path)
    if dir_matches() and current and current.mode == "file"
        and same_open_identity(open_identity, current) then
      -- Path attributes use the normal device number on macOS, unlike
      -- /dev/fd attributes. Sync compares this identity during cleanup.
      return current
    end
    return nil
  end
  local function finish_failure(kind, tmp_name)
    if tmp_name then call("unlinkat", dirfd, tmp_name, 0) end
    call("close", dirfd)
    return false, { kind = kind }
  end
  if not dir_matches() or lfs.symlinkattributes(target_path) then
    return finish_failure("unsafe_path")
  end
  local tmp_name, fd
  for _ = 1, 8 do
    part_counter = part_counter + 1
    tmp_name = ".ghostwriter.part." .. tostring(call("getpid")) .. "."
        .. tostring(os.time()) .. "." .. tostring(part_counter)
    fd = call("openat", dirfd, tmp_name, create_flags, ffi.cast("int", 384)) -- 0600
    if fd >= 0 then break end
  end
  if fd < 0 then return finish_failure("io_error") end
  local tmp_identity = fd_attributes(fd)
  local safe_filename = url.escape(filename)
  local req_url = join_url(server_url, "/api/digests/" .. safe_filename)
  local write_failed = false
  local function sink(chunk)
    if not chunk then return 1 end
    local offset = 0
    while offset < #chunk do
      local written = tonumber(call("write", fd, chunk:sub(offset + 1), #chunk - offset))
      if written <= 0 then
        write_failed = true
        return nil, "Cannot write partial file"
      end
      offset = offset + written
    end
    return 1
  end
  local headers = { ["Accept"] = "application/epub+zip" }
  if token and token ~= "" then headers["Authorization"] = "Bearer " .. token end
  local request = { url = req_url, method = "GET", headers = headers, sink = sink }
  socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
  local request_ok, code, resp_headers, status = pcall(function()
    return socket.skip(1, http.request(request))
  end)
  socketutil:reset_timeout()
  local synced = call("fsync", fd) == 0
  local closed = call("close", fd) == 0
  if write_failed or not synced or not closed then
    return finish_failure("io_error", tmp_name)
  end
  if not request_ok or resp_headers == nil then
    return finish_failure("network_error", tmp_name)
  end
  if code < 200 or code >= 300 then
    return finish_failure("http_error", tmp_name)
  end
  if not dir_matches() then
    return finish_failure("unsafe_path", tmp_name)
  end

  -- Linux renameat2 with NOREPLACE is atomic where the runtime and filesystem
  -- support it. Older kernels/libcs may not expose it, so retain safe fallbacks.
  local rename_available, rename_result = pcall(call, "renameat2", dirfd, tmp_name, dirfd, filename, 1)
  if rename_available and rename_result == 0 then
    local created = finalized_identity(tmp_identity)
    call("close", dirfd)
    if not created then return false, { kind = "unsafe_path" } end
    return true, { path = target_path, created = created }
  end
  if rename_available and ffi.errno() == 17 then
    return finish_failure("collision", tmp_name)
  end
  if call("linkat", dirfd, tmp_name, dirfd, filename, 0) == 0 then
    local created = finalized_identity(tmp_identity)
    call("unlinkat", dirfd, tmp_name, 0)
    call("close", dirfd)
    if not created then return false, { kind = "unsafe_path" } end
    return true, { path = target_path, created = created }
  end
  if ffi.errno() == 17 then
    return finish_failure("collision", tmp_name)
  end

  -- FAT on older kernels may support neither no-replace rename nor links.
  -- Exclusive creation preserves an existing book, though a power loss during
  -- this copy can leave an unowned partial target for manual collision repair.
  local target_fd = call("openat", dirfd, filename, create_flags, ffi.cast("int", 384))
  if target_fd < 0 then
    return finish_failure(ffi.errno() == 17 and "collision" or "io_error", tmp_name)
  end
  local target_identity = fd_attributes(target_fd)
  local function cleanup_target()
    local current = lfs.symlinkattributes(target_path)
    if dir_matches() and target_identity and current and current.mode == "file"
        and same_open_identity(target_identity, current) then
      call("unlinkat", dirfd, filename, 0)
    end
  end
  local source_fd = call("openat", dirfd, tmp_name, 0)
  local copy_ok = source_fd >= 0 and target_identity ~= nil
  local buffer = ffi.new("char[65536]")
  if copy_ok then
    while true do
      local count = tonumber(call("read", source_fd, buffer, 65536))
      if count < 0 then copy_ok = false; break end
      if count == 0 then break end
      local offset = 0
      while offset < count do
        local written = tonumber(call("write", target_fd, buffer + offset, count - offset))
        if written <= 0 then copy_ok = false; break end
        offset = offset + written
      end
      if not copy_ok then break end
    end
  end
  if source_fd >= 0 then call("close", source_fd) end
  if copy_ok then copy_ok = call("fsync", target_fd) == 0 end
  if call("close", target_fd) ~= 0 then copy_ok = false end
  if not copy_ok or not dir_matches() then
    cleanup_target()
    return finish_failure("io_error", tmp_name)
  end
  call("unlinkat", dirfd, tmp_name, 0)
  local created = finalized_identity(target_identity)
  call("close", dirfd)
  if not created then return false, { kind = "unsafe_path" } end
  return true, { path = target_path, created = created }
end

return API
