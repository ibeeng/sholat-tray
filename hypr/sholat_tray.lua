-- Sholat Tray: window rules for Omarchy / Hyprland (app_id "sholat-tray").
-- Installed by install.sh and loaded from hyprland.lua with require("hypr.sholat_tray").

-- Reminder screen (Kartu, Digital, Minimal): floating, on every workspace.
o.window({ class = "^sholat-tray$", title = "^Waktunya .*" }, {
  float = true, pin = true, no_anim = true,
})
-- Running-text banner: top of the screen, every workspace, never steals focus.
o.window({ class = "^sholat-tray$", title = "^Pengingat .*" }, {
  float = true, pin = true, no_initial_focus = true, no_shadow = true,
  border_size = 0, rounding = 0, move = "(monitor_w*0.07) 52",
})
-- Monthly schedule popup: floating and centered.
o.window({ class = "^sholat-tray$", title = "^Jadwal Sholat Bulanan$" }, {
  float = true, center = true, size = { 790, 610 },
})
