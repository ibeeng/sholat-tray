#!/usr/bin/env bash
# Sholat Tray uninstaller. Config dan file adzan TIDAK dihapus.
set -euo pipefail
BIN="$HOME/.local/bin"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN_ID="ibeeng.sholat-tray"

pkill -f "$BIN/sholat-tray\$" 2>/dev/null || true
rm -f "$BIN/sholat-tray" "$BIN/sholat-tray-genmon" \
      "$DATA/icons/hicolor/scalable/apps/sholat-tray.svg" \
      "$DATA/icons/hicolor/symbolic/apps/sholat-tray-symbolic.svg" \
      "$DATA/applications/sholat-tray.desktop" "$CONFIG/autostart/sholat-tray.desktop"

if [[ -d "$CONFIG/hypr" ]]; then
  sed -i '/require("hypr.sholat_tray")/d' "$CONFIG/hypr/hyprland.lua" 2>/dev/null || true
  sed -i '/-- Sholat Tray$/d' "$CONFIG/hypr/autostart.lua" 2>/dev/null || true
  rm -f "$CONFIG/hypr/sholat_tray.lua"
  hyprctl reload >/dev/null 2>&1 || true
fi
if [[ -f "$CONFIG/omarchy/shell.json" ]] && command -v python3 >/dev/null; then
  python3 - "$CONFIG/omarchy/shell.json" "$PLUGIN_ID" <<'PY'
import json, sys
path, pid = sys.argv[1], sys.argv[2]
d = json.load(open(path))
layout = d.get('bar', {}).get('layout', {})
for k, items in layout.items():
    layout[k] = [w for w in items if w.get('id') != pid]
json.dump(d, open(path, 'w'), indent=2)
PY
fi
rm -rf "$CONFIG/omarchy/plugins/$PLUGIN_ID"
echo "Sholat Tray dihapus. Config tersisa di $CONFIG/sholat-tray/"
