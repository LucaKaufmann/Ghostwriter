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
  int mkstemp(char *template);
  long write(int fd, const void *buf, unsigned long count);
  int fsync(int fd);
  int close(int fd);
  int link(const char *oldpath, const char *newpath);
  int unlink(const char *pathname);
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

function API.download_digest(server_url, token, filename, target_path)
  if type(filename) ~= "string" or not filename:match("%.epub$")
      or filename:find("[/\\%c]") or lfs.symlinkattributes(target_path) then
    return false, { kind = "unsafe_path" }
  end
  local safe_filename = url.escape(filename)
  local req_url = join_url(server_url, "/api/digests/" .. safe_filename)

  -- mkstemp gives each attempt a fresh, exclusive .part file. Stale partials
  -- from an interrupted run can be left untouched while a retry proceeds.
  local template = target_path .. ".part.XXXXXX"
  local buffer = ffi.new("char[?]", #template + 1)
  ffi.copy(buffer, template)
  local fd = ffi.C.mkstemp(buffer)
  if fd < 0 then return false, { kind = "io_error", message = "Cannot create partial file" } end
  local tmp_path = ffi.string(buffer)
  local write_failed = false
  local function sink(chunk)
    if not chunk then return 1 end
    local offset = 0
    while offset < #chunk do
      local written = tonumber(ffi.C.write(fd, chunk:sub(offset + 1), #chunk - offset))
      if written <= 0 then
        write_failed = true
        return nil, "Cannot write partial file"
      end
      offset = offset + written
    end
    return 1
  end

  local headers = {
    ["Accept"] = "application/epub+zip",
  }
  if token and token ~= "" then
    headers["Authorization"] = "Bearer " .. token
  end

  local request = {
    url = req_url,
    method = "GET",
    headers = headers,
    sink = sink,
  }

  socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
  local code, resp_headers, status = socket.skip(1, http.request(request))
  socketutil:reset_timeout()

  local synced = ffi.C.fsync(fd) == 0
  local closed = ffi.C.close(fd) == 0
  if write_failed or not synced or not closed then
    ffi.C.unlink(tmp_path)
    return false, { kind = "io_error", message = "Cannot finalize partial file" }
  end

  if resp_headers == nil then
    ffi.C.unlink(tmp_path)
    return false, { kind = "network_error", code = code, status = status }
  end

  if code >= 200 and code < 300 then
    -- POSIX link is atomic and fails if target already exists. os.rename would
    -- silently replace a book created by another process after our check.
    if ffi.C.link(tmp_path, target_path) ~= 0 then
      ffi.C.unlink(tmp_path)
      return false, { kind = "collision_or_unsupported_filesystem" }
    end
    ffi.C.unlink(tmp_path)
    return true, { path = target_path }
  end

  ffi.C.unlink(tmp_path)
  return false, {
    kind = "http_error",
    code = code,
    status = status,
  }
end

return API
