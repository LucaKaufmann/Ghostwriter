local _ = require("gettext")
local Dispatcher = require("dispatcher")
local InfoMessage = require("ui/widget/infomessage")
local MultiInputDialog = require("ui/widget/multiinputdialog")
local SpinWidget = require("ui/widget/spinwidget")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local logger = require("logger")

local const = require("ghostwriter_const")
local GhostwriterSettings = require("ghostwriter_settings")
local GhostwriterSync = require("ghostwriter_sync")

local ghostwriter = WidgetContainer:extend({
  name = "ghostwriter",
  is_doc_only = false,
})

function ghostwriter:init()
  self.settings = GhostwriterSettings:new()
  self:onDispatcherRegisterActions()
  self.ui.menu:registerToMainMenu(self)
end

function ghostwriter:onDispatcherRegisterActions()
  Dispatcher:registerAction("ghostwriter_sync", {
    category = "none",
    event = "GhostwriterSyncNow",
    title = _("Ghostwriter: Sync digests"),
    general = true,
  })
end

function ghostwriter:onGhostwriterSyncNow()
  self:runSync(false)
end

function ghostwriter:addToMainMenu(menu_items)
  menu_items.ghostwriter = {
    text = _("Ghostwriter"),
    sorting_hint = "tools",
    sub_item_table = {
      {
        text = _("Sync digests now"),
        callback = function()
          self:runSync(false)
        end,
      },
      {
        text = _("Configure connection"),
        keep_menu_open = true,
        callback = function()
          self:editConnectionSettings()
        end,
      },
      {
        text_func = function()
          local dir = self.settings:getDownloadDir()
          if dir == "" then
            return _("Download folder: not set")
          end
          return _("Download folder: ") .. dir
        end,
        keep_menu_open = true,
        callback = function(touchmenu_instance)
          self:chooseDownloadDirectory(touchmenu_instance)
        end,
      },
      {
        text_func = function()
          return string.format(_("Keep last N EPUBs: %d"), self.settings:getKeepLastN())
        end,
        keep_menu_open = true,
        callback = function()
          self:editRetentionSetting()
        end,
      },
      {
        text = _("Sync on suspend"),
        checked_func = function()
          return self.settings:getSyncOnSuspendEnabled()
        end,
        callback = function()
          local current = self.settings:getSyncOnSuspendEnabled()
          self.settings:setSyncOnSuspendEnabled(not current)
        end,
      },
      {
        text = _("About Ghostwriter plugin"),
        keep_menu_open = true,
        callback = function()
          UIManager:show(InfoMessage:new({
            text = "Ghostwriter digest sync plugin\n\nVersion: " .. const.VERSION,
          }))
        end,
      },
    },
  }
end

function ghostwriter:editConnectionSettings()
  local dialog = MultiInputDialog:new({
    title = _("Ghostwriter connection"),
    fields = {
      {
        text = self.settings:getServerURL(),
        description = _("Server URL:"),
        hint = _("http://server:8080"),
      },
      {
        text = self.settings:getApiToken(),
        description = _("API token:"),
        hint = _("gw_..."),
      },
    },
    buttons = {
      {
        {
          text = _("Cancel"),
          id = "close",
          callback = function()
            UIManager:close(dialog)
          end,
        },
        {
          text = _("Save"),
          callback = function()
            local values = dialog:getFields()
            self.settings:setServerURL(values[1])
            self.settings:setApiToken(values[2])
            UIManager:close(dialog)
            UIManager:show(InfoMessage:new({ text = _("Connection saved"), timeout = 2 }))
          end,
        },
      },
    },
  })

  UIManager:show(dialog)
  dialog:onShowKeyboard()
end

function ghostwriter:chooseDownloadDirectory(touchmenu_instance)
  require("ui/downloadmgr"):new({
    onConfirm = function(path)
      self.settings:setDownloadDir(path)
      if touchmenu_instance then
        touchmenu_instance:updateItems()
      end
    end,
  }):chooseDir()
end

function ghostwriter:editRetentionSetting()
  local spin = SpinWidget:new({
    value = self.settings:getKeepLastN(),
    value_min = 0,
    value_max = 500,
    value_step = 5,
    value_hold_step = 25,
    title_text = _("Keep last N EPUBs (0 = keep all)"),
    ok_text = _("Save"),
    callback = function(spin_widget)
      self.settings:setKeepLastN(spin_widget.value)
    end,
  })
  UIManager:show(spin)
end

function ghostwriter:onSuspend()
  if self.settings:getSyncOnSuspendEnabled() then
    self:runSync(true)
  end
end

function ghostwriter:onPowerOff()
  if self.settings:getSyncOnSuspendEnabled() then
    self:runSync(true)
  end
end

function ghostwriter:onReboot()
  if self.settings:getSyncOnSuspendEnabled() then
    self:runSync(true)
  end
end

function ghostwriter:runSync(silent)
  local function show_message(text, timeout)
    if not silent then
      UIManager:show(InfoMessage:new({ text = text, timeout = timeout or 3 }))
    end
  end

  local NetworkMgr = require("ui/network/manager")
  NetworkMgr:runWhenOnline(function()
    local progress_message = nil

    if not silent then
      progress_message = InfoMessage:new({ text = _("Ghostwriter sync starting...") })
      UIManager:show(progress_message)
    end

    local ok, sync_ok, sync_payload = pcall(function()
      return GhostwriterSync.run(self.settings, function(progress)
        if silent then
          return
        end

        local text = _("Ghostwriter sync...")
        if progress.phase == "query" then
          text = _("Checking for new digests...")
        elseif progress.phase == "download" then
          text = string.format(
            _("Downloading %d/%d\n%s"),
            progress.current,
            progress.total,
            tostring(progress.filename or "")
          )
        end

        UIManager:close(progress_message)
        progress_message = InfoMessage:new({ text = text })
        UIManager:show(progress_message)
      end)
    end)

    if progress_message then
      UIManager:close(progress_message)
    end

    if not ok then
      logger.err("[Ghostwriter] Sync crashed")
      show_message(_("Sync failed: unexpected error"), 4)
      return
    end

    if not sync_ok then
      show_message(_("Sync failed: ") .. tostring(sync_payload), 4)
      return
    end

    local message = string.format(
      _("Sync complete\nDownloaded: %d\nSkipped existing: %d\nFailed: %d\nPruned: %d"),
      sync_payload.downloaded or 0,
      sync_payload.skipped_existing or 0,
      sync_payload.failed or 0,
      sync_payload.pruned or 0
    )

    show_message(message, 5)
  end)
end

return ghostwriter
