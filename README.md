<div align="center">

# 🕌 Sholat Tray

**Widget pengingat waktu sholat untuk Linux desktop**

Icon tray di panel + poster card overlay muncul otomatis pas waktunya sholat.
Jadwal dari Aladhan API (method 20 = Kemenag Indonesia), lokasi otomatis via IP.

</div>

---

## ✨ Fitur

| Fitur | Detail |
|---|---|
| 🕐 **Tray icon** | Nongol di system panel (deket jam), klik kanan buat jadwal & menu |
| 📍 **Lokasi otomatis** | Deteksi kota via IP geolocation, refresh tiap 30 menit |
| 📅 **Jadwal akurat** | Aladhan API, method 20 = Kemenag Indonesia |
| 🔔 **Notif H-10 menit** | Notifikasi desktop 10 menit sebelum waktu sholat |
| 🌅 **Poster overlay** | Card muncul pas waktunya: sky banner, angled cut, jam besar |
| ⏰ **Snooze** | Tunda 5 menit kalau lagi sibuk |
| 🚪 **Non-intrusif** | Auto-close 10 menit, bisa Esc, nggak fullscreen |
| 🔄 **Offline fallback** | Pakai cache jadwal kalau internet mati |

## 📦 Install

### Cara cepat (1 command)

```bash
git clone https://github.com/ibeeng/sholat-tray.git
cd sholat-tray
bash install.sh
```

### Cara manual (tanpa git)

Download ZIP dari GitHub (tombol hijau **Code** → **Download ZIP**), extract, lalu:

```bash
cd sholat-tray-master
bash install.sh
```

### Apa yang dilakuin installer

1. ✅ Cek dependencies — kalau kurang, tawarin install otomatis via `apt`
2. ✅ Copy app ke `~/bin/sholat-tray.py`
3. ✅ Copy assets ke `~/.cache/`
4. ✅ Generate card background (sky banner + rounded corners)
5. ✅ Pasang autostart (jalan otomatis tiap login)
6. ✅ Start app langsung

## 🖥️ Requirements

| Kebutuhan | Keterangan |
|---|---|
| **OS** | Linux + GTK3 (XFCE, GNOME, Cinnamon, Budgie, dll) |
| **Python** | 3.8+ |
| **Paket apt** | `python3-gi` `gir1.2-gtk-3.0` `gir1.2-ayatanaappindicator3-0.1` `python3-pil` |
| **Font** | Inter (opsional — fallback ke system sans) |
| **Internet** | Untuk fetch jadwal (ada fallback cache kalau offline) |

> **Debian/Ubuntu/Mint**: semua paket ada di repo utama.
> **Fedora**: `sudo dnf install python3-gobject gtk3 libappindicator-gtk3 python3-pillow`
> **Arch**: `sudo pacman -S python-gobject gtk3 libappindicator-gtk3 python-pillow`

## 🎮 Cara Pakai

### Klik kanan icon tray

- Lihat jadwal sholat hari ini (Subuh s/d Isya)
- **Refresh + cek lokasi** — kalau pindah kota/rumah
- **Tes layar pengingat** — preview overlay-nya
- **Jadwal lengkap (browser)** — buka jadwalsholat.org

### Perintah berguna

```bash
# Tes overlay tanpa nunggu maghrib
python3 ~/bin/sholat-tray.py --test-overlay Maghrib

# Stop app
pkill -f sholat-tray.py

# Start manual
python3 ~/bin/sholat-tray.py
```

### Ganti kota (misal pindah rumah)

Edit `~/.config/sholat-kota.conf`:

```ini
AUTO=0
CITY=Bandung
COUNTRY=Indonesia
METHOD=20
```

Simpan, lalu klik kanan tray → **Refresh + cek lokasi**.

> `AUTO=1` (default) = lokasi otomatis via IP. Set `AUTO=0` buat manual.

## 🎨 Kustomisasi Tampilan

### Ganti sky image

1. Siapin gambar landscape (misal foto langit sendiri)
2. Timpa `assets/sholat-sky.jpg`
3. Regenerate:

```bash
python3 gen-card-bg.py
```

### Utak-atik card

Edit `gen-card-bg.py`:

```python
W, H = 640, 560      # ukuran card
CARD_R = 28           # radius sudut rounded
banner_h = H * 0.38   # tinggi sky banner
M_left / M_right      # sudut angled cut
(14, 14, 18)          # warna body
```

Lalu regenerate & restart:

```bash
python3 gen-card-bg.py
pkill -f sholat-tray.py && python3 ~/bin/sholat-tray.py &
```

### Ubah teks pesan

Edit di `bin/sholat-tray.py`, cari `waktunya sholat, bro` — ganti sesuka hati.

## 📁 Struktur Project

```
sholat-tray/
├── bin/
│   └── sholat-tray.py        # App utama: tray + overlay + jadwal
├── assets/
│   ├── sholat-sky.jpg        # Banner langit (bisa diganti)
│   └── sholat-card-bg.png    # Card background (di-generate)
├── gen-card-bg.py            # Generator card background
├── install.sh                # Installer 1-command
└── README.md
```

## ❓ Troubleshooting

**Icon tray nggak muncul**
→ Pastikan panel XFCE punya **Status Tray Plugin / Notification** area. Klik kanan panel → Panel → Add New Items → cari "Status Tray Plugin".

**Overlay nggak muncul pas waktunya**
→ Cek app jalan: `ps aux | grep sholat-tray`. Test manual: `python3 ~/bin/sholat-tray.py --test-overlay Maghrib`

**Jadwal salah / kota salah**
→ Klik kanan tray → Refresh + cek lokasi. Atau set manual di `~/.config/sholat-kota.conf`

**Error `AyatanaAppIndicator3 not found`**
→ `sudo apt install gir1.2-ayatanaappindicator3-0.1`

**Font nggak sama kaya screenshot**
→ Install Inter: [rsms.me/inter](https://rsms.me/inter/) atau `sudo apt install fonts-inter`

## 📸 Preview

Overlay muncul pas waktunya sholat — card kecil di tengah layar, nggak nutupin kerjaan:

- Sky banner maghrib + bulan sabit + bokeh ✨
- Angled cut ke body gelap
- Nama sholat + jam besar + kota
- Tombol **Lanjut kerja** & **Tunda 5 menit**

## 📄 License

MIT — bebas dipakai, dimodif, dibagikan.

---

<div align="center">

**Dibuat dengan 🖤 oleh [ibeeng](https://github.com/ibeeng)**

Kalau berguna, kasih ⭐ ya!

</div>
