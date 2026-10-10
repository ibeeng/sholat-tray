#!/usr/bin/env bash
# Installer sholat-tray untuk XFCE / Linux desktop (GTK3).
# Jalankan: bash install.sh
set -e

HOME_DIR="$HOME"
BIN_DIR="$HOME_DIR/bin"
CONF_DIR="$HOME_DIR/.config"
CACHE_DIR="$HOME_DIR/.cache"
AUTOSTART_DIR="$CONF_DIR/autostart"
PKG_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Sholat Tray installer"
echo "    Home: $HOME_DIR"

# --- 1. dependencies check ---
echo "==> Cek dependencies..."
MISSING=()

python3 -c "import gi" 2>/dev/null || MISSING+=("python3-gi")
python3 -c "gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null || MISSING+=("gir1.2-gtk-3.0")
python3 -c "gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import AyatanaAppIndicator3" 2>/dev/null || MISSING+=("gir1.2-ayatanaappindicator3-0.1")
python3 -c "import PIL" 2>/dev/null || MISSING+=("python3-pil")

if command -v apt-get >/dev/null 2>&1 && [ ${#MISSING[@]} -gt 0 ]; then
    echo "    Paket belum ada: ${MISSING[*]}"
    echo "    Install dengan:"
    echo "      sudo apt install -y ${MISSING[*]}"
    echo
    read -rp "    Mau install sekarang (perlu sudo)? [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
        sudo apt install -y "${MISSING[@]}"
    else
        echo "    Skip. Install manual nanti kalau app gagal jalan."
    fi
elif [ ${#MISSING[@]} -gt 0 ]; then
    echo "    Paket belum ada (install manual): ${MISSING[*]}"
fi

# --- 2. copy app ---
echo "==> Copy app..."
mkdir -p "$BIN_DIR" "$CACHE_DIR"
install -m 755 "$PKG_DIR/bin/sholat-tray.py" "$BIN_DIR/sholat-tray.py"
install -m 644 "$PKG_DIR/assets/sholat-sky.jpg" "$CACHE_DIR/sholat-sky.jpg" 2>/dev/null || true

# --- 3. generate card bg ---
echo "==> Generate card background..."
python3 "$PKG_DIR/gen-card-bg.py" || echo "    (warning) gagal generate card bg — overlay tetap jalan pakai fallback"

# --- 4. autostart ---
echo "==> Pasang autostart..."
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/sholat-tray.desktop" <<EOF
[Desktop Entry]
Name=Waktu Sholat Tray
Comment=Penunjuk waktu sholat di panel XFCE (Kemenag)
Exec=$BIN_DIR/sholat-tray.py
Icon=preferences-system-time
Terminal=false
Type=Application
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

# --- 5. start now (kalau belum jalan) ---
if pgrep -f "$BIN_DIR/sholat-tray.py" >/dev/null 2>&1 || pgrep -f "bin/sholat-tray.py" >/dev/null 2>&1; then
    echo "==> Sholat tray sudah jalan, skip start."
else
    echo "==> Start sholat tray..."
    nohup "$BIN_DIR/sholat-tray.py" >/dev/null 2>&1 &
    sleep 2
    if pgrep -f "sholat-tray.py" >/dev/null 2>&1; then
        echo "    OK, jalan."
    else
        echo "    (warning) belum terdeteksi jalan — coba manual: $BIN_DIR/sholat-tray.py"
    fi
fi

echo
echo "==> Selesai!"
echo "    Icon tray muncul di panel (deket jam)."
echo "    Test overlay : python3 $BIN_DIR/sholat-tray.py --test-overlay Maghrib"
echo "    Stop         : pkill -f sholat-tray.py"
echo "    Auto start   : pas login (autostart sudah dipasang)"
