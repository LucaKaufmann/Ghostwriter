local JSON = require("json")
local logger = require("logger")
local ltn12 = require("ltn12")
local socket = require("socket")
local socketutil = require("socketutil")
local http = require("socket.http")
local url = require("socket.url")

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
  local safe_filename = url.escape(filename)
  local req_url = join_url(server_url, "/api/digests/" .. safe_filename)

  local tmp_path = target_path .. ".part"
  local fh, open_err = io.open(tmp_path, "wb")
  if not fh then
    return false, { kind = "io_error", message = tostring(open_err) }
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
    sink = ltn12.sink.file(fh),
  }

  socketutil:set_timeout(socketutil.LARGE_BLOCK_TIMEOUT, socketutil.LARGE_TOTAL_TIMEOUT)
  local code, resp_headers, status = socket.skip(1, http.request(request))
  socketutil:reset_timeout()

  if resp_headers == nil then
    os.remove(tmp_path)
    return false, { kind = "network_error", code = code, status = status }
  end

  if code >= 200 and code < 300 then
    local renamed, rename_err = os.rename(tmp_path, target_path)
    if not renamed then
      os.remove(tmp_path)
      return false, { kind = "io_error", message = tostring(rename_err) }
    end
    return true, { path = target_path }
  end

  os.remove(tmp_path)
  return false, {
    kind = "http_error",
    code = code,
    status = status,
  }
end

return API
