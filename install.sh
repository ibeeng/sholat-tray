#!/usr/bin/env bash
# Sholat Tray installer (per user, tanpa sudo).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN_ID="ibeeng.sholat-tray"

say()  { printf '\033[1;33m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;31m!!\033[0m %s\n' "$*"; }

# --- cek dependensi ---------------------------------------------------------
missing=()
python3 - <<'PY' 2>/dev/null || missing+=("python-gobject + GTK3 + libayatana-appindicator")
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3
PY
command -v notify-send >/dev/null || missing+=("libnotify (notify-send)")
if ((${#missing[@]})); then
  warn "Dependensi belum ada: ${missing[*]}"
  echo "   Arch/Omarchy : sudo pacman -S python-gobject gtk3 libayatana-appindicator libnotify ffmpeg grim"
  echo "   Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 libnotify-bin ffmpeg"
  exit 1
fi
command -v ffplay >/dev/null || command -v mpg123 >/dev/null || command -v paplay >/dev/null \
  || warn "Tidak ada pemutar audio (ffplay/mpg123/paplay): adzan tidak akan bunyi."

# --- file aplikasi ----------------------------------------------------------
say "Pasang sholat-tray ke $BIN"
install -Dm755 "$SRC/sholat-tray.py" "$BIN/sholat-tray"
install -Dm755 "$SRC/extras/sholat-tray-genmon.sh" "$BIN/sholat-tray-genmon"
install -Dm644 "$SRC/assets/sholat-tray.svg" "$DATA/icons/hicolor/scalable/apps/sholat-tray.svg"
install -Dm644 "$SRC/assets/sholat-tray-symbolic.svg" "$DATA/icons/hicolor/symbolic/apps/sholat-tray-symbolic.svg"
install -Dm644 "$SRC/sholat-tray.desktop" "$DATA/applications/sholat-tray.desktop"
sed -i "s#^Exec=.*#Exec=$BIN/sholat-tray#" "$DATA/applications/sholat-tray.desktop"
gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
mkdir -p "$DATA/sholat-tray"

# --- integrasi desktop ------------------------------------------------------
if command -v omarchy >/dev/null && [[ -d "$CONFIG/hypr" ]]; then
  say "Omarchy terdeteksi: widget bar, window rules, autostart"
  upgrade=0; [[ -d "$CONFIG/omarchy/plugins/$PLUGIN_ID" ]] && upgrade=1
  rm -rf "$CONFIG/omarchy/plugins/$PLUGIN_ID"
  mkdir -p "$CONFIG/omarchy/plugins"
  cp -r "$SRC/plugin/$PLUGIN_ID" "$CONFIG/omarchy/plugins/"

  install -Dm644 "$SRC/hypr/sholat_tray.lua" "$CONFIG/hypr/sholat_tray.lua"
  if ! grep -q 'require("hypr.sholat_tray")' "$CONFIG/hypr/hyprland.lua"; then
    cp "$CONFIG/hypr/hyprland.lua" "$CONFIG/hypr/hyprland.lua.bak.$(date +%s)"
    echo 'require("hypr.sholat_tray")  -- Sholat Tray' >> "$CONFIG/hypr/hyprland.lua"
  fi
  if ! grep -q 'sholat-tray' "$CONFIG/hypr/autostart.lua" 2>/dev/null; then
    echo "o.launch_on_start(\"$BIN/sholat-tray\")  -- Sholat Tray" >> "$CONFIG/hypr/autostart.lua"
  fi
  hyprctl reload >/dev/null 2>&1 || true
  grep -q "\"$PLUGIN_ID\"" "$CONFIG/omarchy/shell.json" 2>/dev/null \
    || omarchy bar put "$PLUGIN_ID" --after omarchy.clock || true
  # shell tidak selalu memuat ulang plugin yang diganti seluruhnya
  ((upgrade)) && omarchy restart shell >/dev/null 2>&1 || true
else
  say "Pasang autostart XDG"
  install -Dm644 "$DATA/applications/sholat-tray.desktop" "$CONFIG/autostart/sholat-tray.desktop"
fi

# --- jalankan ---------------------------------------------------------------
pkill -f "$BIN/sholat-tray\$" 2>/dev/null || true
setsid -f "$BIN/sholat-tray" >/dev/null 2>&1 || true

say "Selesai. Sholat Tray sudah berjalan."
echo "   Adzan: taruh adzan.mp3 dan adzan-fajr.ogg di $DATA/sholat-tray/"
echo "   Config: $CONFIG/sholat-tray/sholat-tray.conf"
