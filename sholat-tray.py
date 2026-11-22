#!/usr/bin/env python3
"""Sholat Tray - pengingat waktu sholat untuk desktop Linux.

Ikon tray (StatusNotifierItem) dengan jadwal sholat harian, notifikasi
10 menit sebelum waktu, layar pengingat saat masuk waktu, dan adzan.
Jalan di Omarchy/Hyprland, XFCE, KDE, dan desktop lain yang punya tray.

- Lokasi otomatis via geolokasi IP (ip-api.com), atau kota manual.
- Sumber jadwal: AlAdhan (koordinat, metode 20 = Kemenag RI) atau
  MyQuran (jadwal resmi kota Indonesia).
- Gaya layar pengingat: Kartu, Digital, Teks berjalan, Minimal;
  warna ikut tema Omarchy atau preset.

Pakai:  sholat-tray            jalankan di latar
        sholat-tray --help     daftar perintah

Config: ~/.config/sholat-tray/sholat-tray.conf
Cache:  ~/.cache/sholat-tray/
Audio:  ~/.local/share/sholat-tray/ (adzan.mp3, adzan-fajr.ogg)

Copyright (c) 2026 ibeeng. Lisensi MIT.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta

os.environ.setdefault('NO_AT_BRIDGE', '1')  # tanpa warning aksesibilitas di terminal

import gi
from gi.repository import GLib as _GLib
_GLib.set_prgname('sholat-tray')  # app_id Wayland -> dipakai window rule Hyprland
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
gi.require_version('PangoCairo', '1.0')
import cairo
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import Gtk, GLib, Gdk, Gio, Pango, PangoCairo

APP_NAME = 'Sholat Tray'
APP_ID = 'sholat-tray'
VERSION = '1.0.0'

HOME = os.path.expanduser('~')
_XDG = lambda var, dflt: os.environ.get(var) or os.path.join(HOME, dflt)
CONF_DIR = os.path.join(_XDG('XDG_CONFIG_HOME', '.config'), APP_ID)
CACHE_DIR = os.path.join(_XDG('XDG_CACHE_HOME', '.cache'), APP_ID)
DATA_DIR = os.path.join(_XDG('XDG_DATA_HOME', '.local/share'), APP_ID)
CONF = os.path.join(CONF_DIR, 'sholat-tray.conf')
LEGACY_CONF = os.path.join(HOME, '.config', 'sholat-kota.conf')
CACHE = os.path.join(CACHE_DIR, 'today.json')
LOCCACHE = os.path.join(CACHE_DIR, 'location.json')

# ikon: ikut terinstal di tema hicolor; fallback ke ikon sistem
ICON = APP_ID
ICON_FALLBACK = 'preferences-system-time'

ORDER = ['Subuh', 'Terbit', 'Dzuhur', 'Ashar', 'Maghrib', 'Isya']
KEYMAP = {'Imsak': 'Imsak', 'Subuh': 'Fajr', 'Terbit': 'Sunrise',
          'Dzuhur': 'Dhuhr', 'Ashar': 'Asr', 'Maghrib': 'Maghrib',
          'Isya': 'Isha'}
# overlay hanya untuk sholat wajib (bukan Terbit)
WAJIB = ['Subuh', 'Dzuhur', 'Ashar', 'Maghrib', 'Isya']
# urutan tampil di menu (termasuk Imsak & Dhuha)
ALL = ['Imsak', 'Subuh', 'Terbit', 'Dhuha', 'Dzuhur', 'Ashar',
       'Maghrib', 'Isya']

# ---- MyQuran API (jadwal resmi kota Indonesia) ----
MYQURAN_CACHE = os.path.join(CACHE_DIR, 'myquran-cities.json')
MYQURAN_BASE = 'https://api.myquran.com/v2/sholat'
MYQURAN_KEYMAP = {'Imsak': 'imsak', 'Subuh': 'subuh', 'Terbit': 'terbit',
                  'Dhuha': 'dhuha', 'Dzuhur': 'dzuhur', 'Ashar': 'ashar',
                  'Maghrib': 'maghrib', 'Isya': 'isya'}

HIJRI_CACHE = os.path.join(CACHE_DIR, 'hijri.json')
HIJRI_MONTHS = ['Muharram', 'Safar', 'Rabiul Awal', 'Rabiul Akhir',
                'Jumadil Awal', 'Jumadil Akhir', 'Rajab', "Sya'ban",
                'Ramadhan', 'Syawal', "Dzulqa'dah", 'Dzulhijjah']

AUDIO_DIR = DATA_DIR
DEFAULT_ADZAN = os.path.join(AUDIO_DIR, 'adzan.mp3')
DEFAULT_ADZAN_FAJR = os.path.join(AUDIO_DIR, 'adzan-fajr.ogg')

UA = f'Mozilla/5.0 (X11; Linux x86_64) {APP_ID}/{VERSION}'


def http_json(url, timeout=15):
    """GET url -> json, pakai User-Agent (banyak API tolak UA default urllib)."""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def migrate_legacy_conf():
    """Pindahkan config lama (~/.config/sholat-kota.conf) sekali saja."""
    if not os.path.exists(CONF) and os.path.exists(LEGACY_CONF):
        os.makedirs(CONF_DIR, exist_ok=True)
        shutil.copy2(LEGACY_CONF, CONF)


def icon_name():
    theme = Gtk.IconTheme.get_default()
    return ICON if theme and theme.has_icon(ICON) else ICON_FALLBACK


def load_conf():
    cfg = {'CITY': 'Jakarta', 'COUNTRY': 'Indonesia', 'METHOD': '20',
           'AUTO': '1', 'SOURCE': 'aladhan',
           'MYQURAN_CITY': '', 'MYQURAN_ID': '',
           'ADZAN': '1', 'ADZAN_VOLUME': '80',
           'ADZAN_FILE': DEFAULT_ADZAN, 'ADZAN_FAJR_FILE': DEFAULT_ADZAN_FAJR}
    try:
        with open(CONF) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


def set_conf(key, value):
    """Tulis/ubah satu key di config tanpa menghapus komentar lain."""
    lines, found = [], False
    try:
        with open(CONF) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        pass
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('#') or '=' not in ln:
            continue
        if ln.split('=', 1)[0].strip() == key:
            lines[i] = f'{key}={value}'
            found = True
            break
    if not found:
        lines.append(f'{key}={value}')
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def add_minutes(hm, mins):
    try:
        t = datetime.strptime(hm, '%H:%M') + timedelta(minutes=mins)
        return t.strftime('%H:%M')
    except Exception:
        return hm


def hijri_today():
    """Tanggal Hijriah hari ini (AlAdhan gToH), cache harian."""
    today = date.today().isoformat()
    try:
        with open(HIJRI_CACHE) as f:
            c = json.load(f)
        if c.get('date') == today:
            return c.get('text')
    except Exception:
        pass
    try:
        d = http_json('https://api.aladhan.com/v1/gToH/'
                      + datetime.now().strftime('%d-%m-%Y'))
        h = d['data']['hijri']
        mnum = int(h['month']['number'])
        mname = HIJRI_MONTHS[mnum - 1] if 1 <= mnum <= 12 else h['month']['en']
        text = f"{int(h['day'])} {mname} {h['year']} H"
        os.makedirs(os.path.dirname(HIJRI_CACHE), exist_ok=True)
        with open(HIJRI_CACHE, 'w') as f:
            json.dump({'date': today, 'text': text}, f)
        return text
    except Exception:
        return None


def detect_location(force=False):
    """Deteksi kota + koordinat via IP. Cache 30 menit."""
    try:
        with open(LOCCACHE) as f:
            loc = json.load(f)
        if not force and time.time() - loc.get('ts', 0) < 1800:
            return loc
    except Exception:
        loc = {}
    try:
        d = http_json(
            'http://ip-api.com/json/?fields=status,city,regionName,'
            'country,lat,lon,query', timeout=10)
        if d.get('status') == 'success':
            loc = {'city': d.get('city') or 'Jakarta',
                   'region': d.get('regionName', ''),
                   'country': d.get('country') or 'Indonesia',
                   'lat': d.get('lat'), 'lon': d.get('lon'),
                   'ts': time.time()}
            os.makedirs(os.path.dirname(LOCCACHE), exist_ok=True)
            with open(LOCCACHE, 'w') as f:
                json.dump(loc, f)
            return loc
    except Exception:
        pass
    return loc or None


def get_place(cfg, force_geo=False):
    """Return dict city/country/lat/lon. AUTO=1 -> geo IP dulu."""
    if cfg.get('AUTO', '1') == '1':
        loc = detect_location(force=force_geo)
        if loc and loc.get('lat'):
            return loc
    return {'city': cfg.get('CITY', 'Jakarta'),
            'country': cfg.get('COUNTRY', 'Indonesia'),
            'lat': None, 'lon': None}


def _myquran_search(name):
    """Cari kota di MyQuran -> (id, lokasi). Prefer KOTA > KAB."""
    url = f'{MYQURAN_BASE}/kota/cari/{urllib.parse.quote(name)}'
    d = http_json(url)
    items = d.get('data') or []
    if not items:
        return None, None
    up = name.upper()

    def score(it):
        lok = (it.get('lokasi') or '').upper()
        s = 10 if up in lok else 0
        s += 3 if 'KOTA' in lok else 0
        return s
    best = max(items, key=score)
    return str(best.get('id')), best.get('lokasi')


def myquran_city_id(cfg, name):
    """Resolve nama kota -> id MyQuran (cache 7 hari)."""
    if cfg.get('MYQURAN_ID'):
        return cfg['MYQURAN_ID'], None
    name = (name or '').strip()
    if not name:
        return None, None
    try:
        with open(MYQURAN_CACHE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    ent = cache.get(name.lower())
    if ent and time.time() - ent.get('ts', 0) < 7 * 86400:
        return ent.get('id'), ent.get('lokasi')
    cid, lokasi = _myquran_search(name)
    if cid:
        cache[name.lower()] = {'id': cid, 'lokasi': lokasi, 'ts': time.time()}
        try:
            os.makedirs(os.path.dirname(MYQURAN_CACHE), exist_ok=True)
            with open(MYQURAN_CACHE, 'w') as f:
                json.dump(cache, f)
        except Exception:
            pass
    return cid, lokasi


def _timings_myquran(cfg, place):
    """Jadwal harian MyQuran -> (timings, lokasi). None kalau gagal."""
    name = cfg.get('MYQURAN_CITY') or place.get('city') or cfg.get('CITY')
    cid, lokasi = myquran_city_id(cfg, name)
    if not cid:
        return None, None
    now = datetime.now()
    url = (f'{MYQURAN_BASE}/jadwal/{cid}/'
           f'{now.year}/{now.month:02d}/{now.day:02d}')
    d = http_json(url)
    j = d['data']['jadwal']
    timings = {id_: j[en][:5] for id_, en in MYQURAN_KEYMAP.items()}
    return timings, (d['data'].get('lokasi') or lokasi or name)


def _timings_aladhan(cfg, place):
    """Jadwal AlAdhan -> timings. by koordinat kalau ada, else by city."""
    if place.get('lat') is not None:
        d = datetime.now().strftime('%d-%m-%Y')
        q = urllib.parse.urlencode({
            'latitude': place['lat'], 'longitude': place['lon'],
            'method': cfg.get('METHOD', '20')})
        url = f'https://api.aladhan.com/v1/timings/{d}?{q}'
    else:
        q = urllib.parse.urlencode({
            'city': place['city'], 'country': place.get('country', 'Indonesia'),
            'method': cfg.get('METHOD', '20')})
        url = f'https://api.aladhan.com/v1/timingsByCity?{q}'
    data = http_json(url)
    t = data['data']['timings']
    timings = {id_: t[en].split()[0] for id_, en in KEYMAP.items() if en in t}
    # AlAdhan tak sediakan Dhuha -> estimasi Terbit + 30 menit
    if 'Dhuha' not in timings:
        timings['Dhuha'] = add_minutes(timings.get('Terbit', '05:30'), 30)
    return timings


def fetch_timings(cfg, place):
    today = date.today().isoformat()
    source = cfg.get('SOURCE', 'aladhan').strip().lower()
    cache_key = f"{source}:{place.get('city')}"
    try:
        with open(CACHE) as f:
            c = json.load(f)
        if c.get('date') == today and c.get('key') == cache_key:
            if c.get('city'):
                place['city_display'] = c['city']
            return c['timings']
    except Exception:
        pass

    timings = None
    city_display = place.get('city')
    try:
        if source == 'myquran':
            timings, disp = _timings_myquran(cfg, place)
            if disp:
                city_display = disp
        if timings is None:
            timings = _timings_aladhan(cfg, place)
    except Exception:
        timings = None

    if timings is None:
        try:
            with open(CACHE) as f:
                return json.load(f)['timings']
        except Exception:
            timings = {'Imsak': '04:30', 'Subuh': '04:40', 'Terbit': '05:50',
                       'Dhuha': '06:20', 'Dzuhur': '11:50', 'Ashar': '15:10',
                       'Maghrib': '18:00', 'Isya': '19:10'}
    if city_display:
        place['city_display'] = city_display
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, 'w') as f:
            json.dump({'date': today, 'city': city_display, 'key': cache_key,
                       'timings': timings}, f)
    except Exception:
        pass
    return timings


def _month_myquran(cfg, place, year, month):
    name = cfg.get('MYQURAN_CITY') or place.get('city') or cfg.get('CITY')
    cid, _ = myquran_city_id(cfg, name)
    if not cid:
        return None
    d = http_json(f'{MYQURAN_BASE}/jadwal/{cid}/{year}/{month:02d}')
    rows = []
    for r in d['data']['jadwal']:
        rows.append({'raw': r.get('tanggal', ''), 'iso': r.get('date', ''),
                     **{k: r[v] for k, v in MYQURAN_KEYMAP.items() if v in r}})
    return rows


def _month_aladhan(cfg, place, year, month):
    if place.get('lat') is not None:
        q = urllib.parse.urlencode({
            'latitude': place['lat'], 'longitude': place['lon'],
            'method': cfg.get('METHOD', '20')})
    else:
        q = urllib.parse.urlencode({
            'city': place.get('city'),
            'country': place.get('country', 'Indonesia'),
            'method': cfg.get('METHOD', '20')})
    d = http_json(f'https://api.aladhan.com/v1/calendar/{year}/{month}?{q}')
    rows = []
    for day in d['data']:
        t = day['timings']
        row = {k: t[v].split()[0] for k, v in KEYMAP.items() if v in t}
        row['Dhuha'] = add_minutes(row.get('Terbit', '05:30'), 30)
        g = day['date']['gregorian']
        iso = f"{g['year']}-{int(g['month']['number']):02d}-{int(g['day']):02d}"
        row['iso'] = iso
        wd = HARI[datetime.strptime(iso, '%Y-%m-%d').weekday()]
        row['raw'] = f"{wd}, {g['day']}/{g['month']['number']}/{g['year']}"
        rows.append(row)
    return rows


def fetch_month(cfg, place, year, month):
    """Jadwal 1 bulan penuh -> list dict (kunci Imsak..Isya + raw)."""
    source = cfg.get('SOURCE', 'aladhan').strip().lower()
    try:
        if source == 'myquran':
            rows = _month_myquran(cfg, place, year, month)
            if rows:
                return rows
        return _month_aladhan(cfg, place, year, month)
    except Exception as e:
        print('fetch_month gagal:', e)
        return _month_aladhan(cfg, place, year, month)


def next_prayer(timings):
    now = datetime.now().strftime('%H:%M')
    for name in ORDER:
        if timings.get(name, '') > now:
            return name, timings[name]
    return 'Subuh', timings.get('Subuh', '04:30')


def minutes_to(target_hm):
    try:
        t = datetime.strptime(target_hm, '%H:%M').replace(
            year=datetime.now().year, month=datetime.now().month,
            day=datetime.now().day)
        diff = (t - datetime.now()).total_seconds()
        if diff < 0:
            diff += 86400
        return int(diff // 60)
    except Exception:
        return 9999


def countdown(target_hm):
    m = minutes_to(target_hm)
    h, mm = m // 60, m % 60
    return f'{h}j{mm:02d}m' if h else f'{mm}m'


# ---------- TEMA ----------
OMARCHY_COLORS = os.path.join(HOME, '.local', 'state', 'omarchy', 'current',
                              'theme', 'colors.toml')
# preset: bg, body, sky (3 stop banner), accent, text
THEMES = {
    'senja': {'label': 'Senja (emas)', 'bg': '#0b0b10', 'body': '#111216',
              'sky': ['#0f2a4a', '#2d5f8a', '#e9a85b'],
              'accent': '#f5c542', 'text': '#ffffff'},
    'subuh': {'label': 'Subuh (biru fajar)', 'bg': '#06080f', 'body': '#0e1220',
              'sky': ['#08142b', '#274b7a', '#e9c4a8'],
              'accent': '#8fc8ff', 'text': '#f4f7ff'},
    'masjid': {'label': 'Masjid (hijau-emas)', 'bg': '#040806', 'body': '#0d1511',
               'sky': ['#062b20', '#0f5c45', '#c9a64a'],
               'accent': '#d4af37', 'text': '#f3f7f2'},
    'malam': {'label': 'Malam (ungu)', 'bg': '#050509', 'body': '#0f1018',
              'sky': ['#050816', '#1b2340', '#6d6aa8'],
              'accent': '#b7b4ff', 'text': '#f2f1ff'},
}
THEME_ORDER = ['omarchy', 'senja', 'subuh', 'masjid', 'malam']
THEME_LABEL_OMARCHY = 'Ikut tema Omarchy'


def _rgb(h):
    h = h.lstrip('#')[:6]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Campur warna hex a -> b sebanyak t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t)
                                   for x, y in zip(ra, rb))


def rgba(h, alpha):
    r, g, b = _rgb(h)
    return f'rgba({r},{g},{b},{alpha})'


def _lum(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _omarchy_base():
    """Palet dari tema Omarchy aktif (colors.toml). None kalau tak ada."""
    try:
        import tomllib
        with open(OMARCHY_COLORS, 'rb') as f:
            c = tomllib.load(f)
        ok = lambda v: isinstance(v, str) and v.startswith('#') and len(v) >= 7
        bg = c.get('background') if ok(c.get('background')) else None
        fg = c.get('foreground') if ok(c.get('foreground')) else None
        acc = c.get('accent') if ok(c.get('accent')) else None
        if not (bg and fg and acc):
            return None
        dark = c.get('darker_background') if ok(c.get('darker_background')) else bg
        sel = c.get('selection') if ok(c.get('selection')) else mix(bg, acc, 0.4)
        return {'bg': bg, 'body': mix(bg, fg, 0.04),
                'sky': [dark, sel, acc], 'accent': acc, 'text': fg}
    except Exception as e:
        print('baca tema omarchy gagal:', e)
        return None


def palette(cfg=None):
    """Palet lengkap sesuai TEMA di config (default: omarchy, fallback senja)."""
    cfg = cfg or load_conf()
    name = (os.environ.get('SHOLAT_TRAY_COLOR') or cfg.get('TEMA')
            or 'omarchy').strip().lower()
    base = _omarchy_base() if name == 'omarchy' else THEMES.get(name)
    if not base:
        base = THEMES['senja']
    bg, text, acc = base['bg'], base['text'], base['accent']
    return {
        'bg': bg, 'body': base['body'], 'sky': base['sky'],
        'accent': acc, 'text': text,
        'accent_hi': mix(acc, text, 0.3),
        'on_accent': '#111214' if _lum(acc) > 0.55 else '#ffffff',
        'alt': mix(bg, text, 0.035),
        'text2': mix(text, bg, 0.12),
        'sub': mix(text, bg, 0.3),
        'muted': mix(text, bg, 0.48),
        'faint': mix(text, bg, 0.58),
        'today_bg': mix(bg, acc, 0.13),
        'today_text': mix(acc, text, 0.35),
        'today_sub': mix(acc, bg, 0.2),
        'sky_text': '#ffffff' if _lum(base['sky'][0]) < 0.5 else '#111214',
    }


_OVERLAY_PROV = None


# ---------- FULLSCREEN OVERLAY (blur) ----------

BLUR_BG = os.path.join(CACHE_DIR, 'blur-bg.png')


def screen_size():
    """Ukuran logis monitor utama (Wayland-safe)."""
    try:
        disp = Gdk.Display.get_default()
        mon = disp.get_primary_monitor() or disp.get_monitor(0)
        g = mon.get_geometry()
        return g.width, g.height
    except Exception:
        return 1366, 768


def grab_blur_bg_wayland(path=BLUR_BG, dark=0.55):
    """Wayland: grim (skala kecil) -> ffmpeg blur + gelapin -> ukuran layar."""
    if not (shutil.which('grim') and shutil.which('ffmpeg')):
        return None
    w, h = screen_size()
    raw = path + '.raw.png'
    try:
        subprocess.run(['grim', '-s', '0.15', raw], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bright = -(dark * 0.6)
        vf = (f'gblur=sigma=4,scale={w}:{h}:flags=bilinear,'
              f'eq=brightness={bright:.2f}:saturation=0.8')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
                        '-vf', vf, '-frames:v', '1', path],
                       check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return path
    except Exception as e:
        print('blur bg (grim) gagal:', e)
        return None
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass


def grab_blur_bg(path=BLUR_BG, dark=0.55):
    """Screenshot desktop -> blur halus + gelapin. Return path / None."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.environ.get('WAYLAND_DISPLAY'):
        return grab_blur_bg_wayland(path, dark)
    try:
        from PIL import Image, ImageFilter
        screen = Gdk.Screen.get_default()
        root = screen.get_root_window()
        w, h = root.get_width(), root.get_height()
        pb = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
        if pb is None:
            return None
        nch = pb.get_n_channels()
        mode = 'RGB' if nch == 3 else 'RGBA'
        img = Image.frombytes(
            mode, (pb.get_width(), pb.get_height()),
            pb.get_pixels(), 'raw', mode, pb.get_rowstride())
        img = img.convert('RGB')
        small_w = 200
        small_h = max(1, int(small_w * h / max(w, 1)))
        small = img.resize((small_w, small_h), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(10))
        bg = small.resize((w, h), Image.BILINEAR)
        black = Image.new('RGB', (w, h), (4, 4, 10))
        bg = Image.blend(bg, black, dark)
        bg.save(path)
        return path
    except Exception as e:
        print('blur bg gagal:', e)
        return None


def apply_overlay_css(P):
    """CSS bersama semua gaya layar pengingat (satu provider, di-reload)."""
    css = (
        f"#sholat-overlay {{ background: {P['bg']}; }}"
        "#sholat-overlay * { font-family: Inter, 'Inter Display', 'Segoe UI', Cantarell, sans-serif; }"
        f".btn-gold {{ background: {P['accent']}; color: {P['on_accent']};"
        " border: none; border-radius: 999px; font-weight: 900;"
        f" box-shadow: 0 10px 40px {rgba(P['accent'], 0.35)},"
        f" 0 0 24px {rgba(P['accent'], 0.25)}; }}"
        f".btn-gold:hover {{ background: {P['accent_hi']}; }}"
        ".btn-text { background: transparent; border: none;"
        " box-shadow: none; text-shadow: none; outline: none;"
        f" color: {P['muted']}; font-weight: 700; }}"
        f".btn-text:hover {{ color: {P['accent']}; }}"
        ".sholat-card { border-radius: 28px;"
        f" background-image: linear-gradient(170deg, {P['sky'][0]} 0%,"
        f" {P['sky'][1]} 30%, {P['sky'][2]} 52%,"
        f" {mix(P['body'], P['text'], 0.02)} 52.4%, {P['body']} 100%);"
        " box-shadow: 0 30px 80px rgba(0,0,0,0.6);"
        f" border: 1px solid {rgba(P['text'], 0.06)}; }}"
        "#sholat-marquee { background: transparent; }"
    )
    global _OVERLAY_PROV
    if _OVERLAY_PROV is None:
        _OVERLAY_PROV = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), _OVERLAY_PROV,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _OVERLAY_PROV.load_from_data(css.encode())


def _esc(v):
    return GLib.markup_escape_text(str(v))


def _set_rgb(cr, hexcol, alpha=1.0):
    r, g, b = _rgb(hexcol)
    cr.set_source_rgba(r / 255, g / 255, b / 255, alpha)


def _pango_layout(cr, text, family, px, weight=Pango.Weight.NORMAL,
                  spacing=0):
    lay = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription()
    fd.set_family(family)
    fd.set_absolute_size(max(1, px) * Pango.SCALE)
    fd.set_weight(weight)
    lay.set_font_description(fd)
    if spacing:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        lay.set_attributes(attrs)
    lay.set_text(text, -1)
    return lay


def _draw_text(cr, lay, x, y, hexcol, alpha=1.0, align='center'):
    w, h = lay.get_pixel_size()
    if align == 'center':
        x -= w / 2
    elif align == 'right':
        x -= w
    _set_rgb(cr, hexcol, alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, lay)
    return w, h


def elapsed_label(jam):
    """'+MM:SS' sejak waktu sholat (atau '-MM:SS' kalau belum masuk)."""
    try:
        now = datetime.now()
        t = datetime.strptime(jam, '%H:%M').replace(
            year=now.year, month=now.month, day=now.day)
        d = int((now - t).total_seconds())
    except Exception:
        return ''
    sign = '+' if d >= 0 else '-'
    d = abs(d)
    if d >= 3600:
        return f'{sign}{d // 3600}:{d % 3600 // 60:02d}:{d % 60:02d}'
    return f'{sign}{d // 60:02d}:{d % 60:02d}'


class ReminderBase(Gtk.Window):
    """Dasar semua gaya layar pengingat: tanpa dekorasi, Esc menutup,
    tombol Tutup/Tunda, auto-tutup 10 menit."""

    FULLSCREEN = True

    def __init__(self, title, snooze_cb=None):
        super().__init__(title=title)
        self.snooze_cb = snooze_cb
        self.P = palette()
        self.set_name('sholat-overlay')
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        apply_overlay_css(self.P)
        self.connect('key-press-event', self.on_key)
        self.btn_close = None

    def action_buttons(self, vertical=True):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical
                      else Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_close = Gtk.Button(label='Tutup')
        self.btn_close.get_style_context().add_class('btn-gold')
        self.btn_close.set_size_request(170, 44)
        self.btn_close.connect('clicked', lambda *_: self.destroy())
        snooze = Gtk.Button(label='Tunda 5 menit')
        snooze.get_style_context().add_class('btn-text')
        snooze.connect('clicked', self.on_snooze)
        box.pack_start(self.btn_close, False, False, 0)
        box.pack_start(snooze, False, False, 0)
        return box

    def finish(self):
        if self.FULLSCREEN:
            # ukuran layar penuh dari awal; fullscreen() setelah tampil,
            # karena Hyprland mengabaikan permintaan sebelum window di-map
            self.set_size_request(*screen_size())
        self.show_all()
        if self.FULLSCREEN:
            GLib.idle_add(lambda: (self.fullscreen(), False)[1])
        self.present()
        if self.btn_close:
            self.btn_close.grab_focus()  # Enter = tutup
        GLib.timeout_add_seconds(600, self.auto_close)

    def on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def on_snooze(self, *_):
        if self.snooze_cb:
            self.snooze_cb()
        self.destroy()

    def auto_close(self):
        try:
            self.destroy()
        except Exception:
            pass
        return False


class MinimalOverlay(ReminderBase):
    """Gaya Minimal: tulisan besar di tengah, di atas desktop yang di-blur."""

    def __init__(self, prayer, jam, city, snooze_cb=None):
        super().__init__(f'Waktunya {prayer}', snooze_cb)
        P = self.P
        overlay = Gtk.Overlay()
        bg = grab_blur_bg(dark=0.45)
        if bg:
            img = Gtk.Image.new_from_file(bg)
            img.set_hexpand(True)
            img.set_vexpand(True)
            overlay.add(img)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        col.set_halign(Gtk.Align.CENTER)
        col.set_valign(Gtk.Align.CENTER)

        def lbl(markup, top=0):
            w = Gtk.Label()
            w.set_markup(markup)
            w.set_justify(Gtk.Justification.CENTER)
            w.set_margin_top(top)
            col.pack_start(w, False, False, 0)
            return w

        lbl(f'<span size="13000" weight="bold" letter_spacing="4000" '
            f'color="{P["accent"]}">WAKTU SHOLAT</span>')
        lbl(f'<span size="30000" color="{P["text2"]}">'
            'حَيَّ عَلَى '
            'الصَّلَاةِ'
            '</span>', top=10)
        lbl(f'<span size="96000" weight="800" letter_spacing="-1500" '
            f'color="{P["text"]}">{_esc(prayer)}</span>')
        lbl(f'<span size="16000" color="{P["sub"]}">{_esc(jam)}  ·  '
            f'{_esc(city)}</span>')
        rule = Gtk.Label()
        rule.set_markup(f'<span size="9000" color="{P["accent"]}">———</span>')
        rule.set_margin_top(18)
        rule.set_margin_bottom(22)
        col.pack_start(rule, False, False, 0)
        btns = self.action_buttons(vertical=False)
        btns.set_halign(Gtk.Align.CENTER)
        col.pack_start(btns, False, False, 0)
        hint = Gtk.Label()
        hint.set_markup(f'<span size="9500" color="{P["faint"]}">Esc untuk menutup</span>')
        hint.set_margin_top(14)
        col.pack_start(hint, False, False, 0)
        if bg:
            overlay.add_overlay(col)
        else:
            overlay.add(col)
        self.add(overlay)
        self.finish()


# ----- Digital: jam 7-segmen ala papan LED -----
SEG7 = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
        '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg',
        '9': 'abcdfg'}


def _seg_paths(x, y, w, h, t):
    """Poligon tiap segmen (a-g) untuk satu digit."""
    g = t * 0.16
    cy = {'a': y + t / 2, 'g': y + h / 2, 'd': y + h - t / 2}
    x0, x1 = x + t / 2 + g, x + w - t / 2 - g

    def hseg(c):
        return [(x0, c), (x0 + t / 2, c - t / 2), (x1 - t / 2, c - t / 2),
                (x1, c), (x1 - t / 2, c + t / 2), (x0 + t / 2, c + t / 2)]

    def vseg(cx, y0, y1):
        return [(cx, y0), (cx + t / 2, y0 + t / 2), (cx + t / 2, y1 - t / 2),
                (cx, y1), (cx - t / 2, y1 - t / 2), (cx - t / 2, y0 + t / 2)]
    lx, rx = x + t / 2, x + w - t / 2
    up0, up1 = y + t / 2 + g, y + h / 2 - g
    lo0, lo1 = y + h / 2 + g, y + h - t / 2 - g
    return {'a': hseg(cy['a']), 'g': hseg(cy['g']), 'd': hseg(cy['d']),
            'f': vseg(lx, up0, up1), 'b': vseg(rx, up0, up1),
            'e': vseg(lx, lo0, lo1), 'c': vseg(rx, lo0, lo1)}


def draw_seg7(cr, text, x, y, dh, on, off_alpha=0.07, glow=True,
              colon_on=True):
    """Gambar string digit/':' bergaya 7-segmen. Return lebar total."""
    dw, t = dh * 0.54, dh * 0.12
    gap, colon = dw * 0.26, t * 2.4
    cx = x
    for ch in text:
        if ch == ':':
            for fy in (0.32, 0.68):
                _set_rgb(cr, on, 1.0 if colon_on else 0.12)
                cr.rectangle(cx + colon / 2 - t / 2, y + dh * fy - t / 2, t, t)
                cr.fill()
            cx += colon + gap
            continue
        lit = SEG7.get(ch, '')
        for name, pts in _seg_paths(cx, y, dw, dh, t).items():
            cr.move_to(*pts[0])
            for pt in pts[1:]:
                cr.line_to(*pt)
            cr.close_path()
            if name in lit:
                if glow:
                    _set_rgb(cr, on, 0.22)
                    cr.set_line_width(t * 0.9)
                    cr.stroke_preserve()
                _set_rgb(cr, on)
                cr.fill()
            else:
                _set_rgb(cr, on, off_alpha)
                cr.fill()
        cx += dw + gap
    return cx - gap - x


def seg7_width(text, dh):
    dw, t = dh * 0.54, dh * 0.12
    gap, colon = dw * 0.26, t * 2.4
    return sum((colon if c == ':' else dw) + gap for c in text) - gap


class DigitalOverlay(ReminderBase):
    """Gaya Digital: jam 7-segmen besar yang berdetak, ala jam masjid."""

    MONO = 'JetBrainsMono Nerd Font, JetBrains Mono, DejaVu Sans Mono, monospace'

    def __init__(self, prayer, jam, city, snooze_cb=None):
        super().__init__(f'Waktunya {prayer}', snooze_cb)
        self.prayer, self.jam, self.city = prayer, jam, city
        overlay = Gtk.Overlay()
        da = Gtk.DrawingArea()
        da.connect('draw', self.on_draw)
        overlay.add(da)
        btns = self.action_buttons(vertical=False)
        btns.set_halign(Gtk.Align.CENTER)
        btns.set_valign(Gtk.Align.END)
        btns.set_margin_bottom(int(screen_size()[1] * 0.09))
        overlay.add_overlay(btns)
        self.add(overlay)
        self._tick = GLib.timeout_add(250, lambda: (da.queue_draw(), True)[1])
        self.connect('destroy', lambda *_: GLib.source_remove(self._tick))
        self.finish()

    def on_draw(self, w, cr):
        P = self.P
        W, H = w.get_allocated_width(), w.get_allocated_height()
        base = mix(P['bg'], '#000000', 0.55)
        _set_rgb(cr, base)
        cr.paint()
        # vignette
        grad = cairo.RadialGradient(W / 2, H * 0.45, H * 0.1, W / 2, H * 0.45, W * 0.75)
        r, g, b = (c / 255 for c in _rgb(P['accent']))
        grad.add_color_stop_rgba(0, r, g, b, 0.07)
        grad.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(grad)
        cr.paint()
        # scanlines
        _set_rgb(cr, P['text'], 0.018)
        for yy in range(0, H, 3):
            cr.rectangle(0, yy, W, 1)
        cr.fill()

        now = datetime.now()
        cap = _pango_layout(cr, f'WAKTU SHOLAT  ·  {self.city.upper()}',
                            self.MONO, H * 0.022, Pango.Weight.BOLD, H * 0.006)
        _draw_text(cr, cap, W / 2, H * 0.14, P['muted'])
        name = _pango_layout(cr, self.prayer.upper(), self.MONO, H * 0.085,
                             Pango.Weight.HEAVY, H * 0.02)
        _draw_text(cr, name, W / 2, H * 0.19, P['accent'])

        dh = H * 0.27
        ss_h = dh * 0.36
        total = seg7_width('88:88', dh) + dh * 0.18 + seg7_width('88', ss_h)
        x = (W - total) / 2
        y = H * 0.36
        cr.save()
        cr.translate(W / 2, y + dh / 2)
        cr.transform(cairo.Matrix(1, 0, -0.07, 1, 0, 0))  # miring ala LED
        cr.translate(-W / 2, -(y + dh / 2))
        draw_seg7(cr, now.strftime('%H:%M'), x, y, dh, P['accent'],
                  colon_on=now.second % 2 == 0)
        sx = x + seg7_width('88:88', dh) + dh * 0.18
        draw_seg7(cr, now.strftime('%S'), sx, y + dh - ss_h, ss_h, P['accent'])
        cr.restore()

        info = _pango_layout(
            cr, f'ADZAN {self.jam}   ·   {elapsed_label(self.jam)}',
            self.MONO, H * 0.026, Pango.Weight.BOLD, H * 0.004)
        _draw_text(cr, info, W / 2, y + dh + H * 0.07, P['sub'])
        return False


class MarqueeOverlay(ReminderBase):
    """Gaya Teks berjalan: banner tipis ala papan running text masjid.
    Tidak menutup layar; klik untuk menutup."""

    FULLSCREEN = False
    MONO = DigitalOverlay.MONO
    SPEED = 110  # px/detik

    def __init__(self, prayer, jam, city, snooze_cb=None):
        super().__init__(f'Pengingat {prayer}', snooze_cb)
        self.set_name('sholat-marquee')
        self.prayer, self.jam, self.city = prayer, jam, city
        sw, sh = screen_size()
        self.W, self.H = int(sw * 0.86), 96
        self.set_default_size(self.W, self.H)
        self.set_size_request(self.W, self.H)
        self.set_accept_focus(False)
        if not os.environ.get('WAYLAND_DISPLAY'):
            self.set_position(Gtk.WindowPosition.NONE)
            self.move((sw - self.W) // 2, 56)
        arab = ('حَيَّ عَلَى '
                'الصَّلَاةِ')
        self.text = (f'✦  Telah masuk waktu sholat {prayer} pukul {jam} '
                     f'untuk wilayah {city} dan sekitarnya   ✦   {arab}   '
                     '✦   Mari tunaikan sholat   ')
        self.t0 = time.monotonic()
        da = Gtk.DrawingArea()
        da.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        da.connect('draw', self.on_draw)
        da.connect('button-press-event', self.on_click)
        da.set_tooltip_text('Klik kiri: tutup  ·  Klik kanan: tunda 5 menit')
        self.add(da)
        self._tick = GLib.timeout_add(16, lambda: (da.queue_draw(), True)[1])
        self.connect('destroy', lambda *_: GLib.source_remove(self._tick))
        self.show_all()
        GLib.timeout_add_seconds(240, self.auto_close)

    def on_click(self, _w, ev):
        if ev.button == 3:
            self.on_snooze()
        else:
            self.destroy()
        return True

    def on_draw(self, w, cr):
        P = self.P
        W, H = w.get_allocated_width(), w.get_allocated_height()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        rad = 16

        def rrect(x, y, ww, hh, r):
            cr.new_sub_path()
            cr.arc(x + ww - r, y + r, r, -1.5708, 0)
            cr.arc(x + ww - r, y + hh - r, r, 0, 1.5708)
            cr.arc(x + r, y + hh - r, r, 1.5708, 3.1416)
            cr.arc(x + r, y + r, r, 3.1416, 4.7124)
            cr.close_path()
        panel = mix(P['bg'], '#000000', 0.5)
        rrect(0.5, 0.5, W - 1, H - 1, rad)
        _set_rgb(cr, panel)
        cr.fill_preserve()
        _set_rgb(cr, P['accent'], 0.45)
        cr.set_line_width(1)
        cr.stroke()

        # badge kiri: nama sholat + jam
        bw = int(H * 2.1)
        cr.save()
        rrect(6, 6, bw, H - 12, rad - 5)
        cr.clip()
        _set_rgb(cr, P['accent'])
        cr.paint()
        cr.restore()
        n = _pango_layout(cr, self.prayer.upper(), self.MONO, H * 0.25,
                          Pango.Weight.HEAVY, 2)
        _draw_text(cr, n, 6 + bw / 2, H * 0.17, P['on_accent'])
        j = _pango_layout(cr, self.jam, self.MONO, H * 0.27, Pango.Weight.BOLD)
        _draw_text(cr, j, 6 + bw / 2, H * 0.47, P['on_accent'], 0.85)

        # area teks berjalan
        x0, x1 = bw + 22, W - 16
        cr.save()
        cr.rectangle(x0, 8, x1 - x0, H - 16)
        cr.clip()
        lay = _pango_layout(cr, self.text, self.MONO, H * 0.4, Pango.Weight.BOLD)
        tw, th = lay.get_pixel_size()
        off = ((time.monotonic() - self.t0) * self.SPEED) % tw
        x = x1 - off - tw  # mulai dari kanan, berjalan ke kiri
        while x < x1:
            _set_rgb(cr, P['accent'], 0.25)
            cr.move_to(x, (H - th) / 2 + 1)
            PangoCairo.show_layout(cr, lay)
            _set_rgb(cr, P['accent_hi'])
            cr.move_to(x, (H - th) / 2)
            PangoCairo.show_layout(cr, lay)
            x += tw
        # efek dot-matrix LED
        _set_rgb(cr, panel, 0.55)
        for xx in range(int(x0), int(x1), 4):
            cr.rectangle(xx, 0, 1.3, H)
        for yy in range(0, H, 4):
            cr.rectangle(x0, yy, x1 - x0, 1.3)
        cr.fill()
        cr.restore()
        return False


class BreakOverlay(ReminderBase):
    """Gaya Kartu: wallpaper ter-blur + kartu poster. Tutup: tombol / Esc."""
    def __init__(self, prayer, jam, city, snooze_cb=None):
        super().__init__(f'Waktunya {prayer}', snooze_cb)
        esc = _esc
        P = self.P

        overlay = Gtk.Overlay()

        # --- LAYER 0: wallpaper blur (fullscreen) ---
        bg = grab_blur_bg()
        if bg:
            bg_img = Gtk.Image.new_from_file(bg)
            bg_img.set_hexpand(True)
            bg_img.set_vexpand(True)
            overlay.add(bg_img)

        # --- LAYER 1: kartu poster (sky banner + angled cut + body) ---
        # kartu digambar via CSS: banner langit di atas, body polos
        card_img = Gtk.Box()
        card_img.set_size_request(640, 560)
        card_img.get_style_context().add_class('sholat-card')
        card_img.set_halign(Gtk.Align.CENTER)
        card_img.set_valign(Gtk.Align.CENTER)

        # --- LAYER 2: konten di atas kartu ---
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        content.set_size_request(640, 560)

        # top-right header ala mockup
        hdr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hdr.set_halign(Gtk.Align.END)
        hdr.set_valign(Gtk.Align.START)
        hdr.set_margin_top(30); hdr.set_margin_end(36)
        t1 = Gtk.Label()
        t1.set_markup(f'<span size="15000" weight="bold" color="{P["sky_text"]}">SHOLAT TRAY</span>')
        t1.set_halign(Gtk.Align.END)
        t2 = Gtk.Label()
        t2.set_markup(f'<span size="12000" color="{P["sky_text"]}" alpha="85%">Pengingat waktu sholat</span>')
        t2.set_halign(Gtk.Align.END)
        line = Gtk.Label()
        line.set_markup(f'<span size="8000" color="{P["sky_text"]}">──────────────</span>')
        line.set_halign(Gtk.Align.END)
        for w in (t1, t2, line):
            hdr.pack_start(w, False, False, 0)
        content.pack_start(hdr, False, False, 0)

        # spacer fleksibel sampai bagian bawah card
        spacer = Gtk.Box()
        content.pack_start(spacer, True, True, 0)

        # label "Daily memo" style
        lbl_cat = Gtk.Label()
        lbl_cat.set_markup(
            f'<span size="23000" weight="bold" color="{P["text"]}">{esc(prayer)}</span>')
        lbl_cat.set_halign(Gtk.Align.START)
        lbl_cat.set_margin_start(48)
        lbl_cat.set_margin_bottom(4)
        lbl_sub = Gtk.Label()
        lbl_sub.set_markup(
            f'<span size="13500" color="{P["sub"]}">{esc(jam)} \u2022 {esc(city)} \u2014 sudah masuk waktu sholat.</span>')
        lbl_sub.set_halign(Gtk.Align.START)
        lbl_sub.set_margin_start(48)
        lbl_sub.set_margin_bottom(26)

        # bottom row: jam besar + tombol
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        bottom.set_halign(Gtk.Align.FILL)
        bottom.set_margin_start(48); bottom.set_margin_end(48)
        bottom.set_margin_bottom(46)

        big_time = Gtk.Label()
        big_time.set_markup(
            f'<span size="48000" weight="heavy" color="{P["text"]}" letter_spacing="-500">{esc(jam)}</span>')
        big_time.set_valign(Gtk.Align.END)
        big_time.set_halign(Gtk.Align.START)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        actions.set_valign(Gtk.Align.END)
        actions.set_halign(Gtk.Align.END)
        actions = self.action_buttons()
        actions.set_valign(Gtk.Align.END)
        actions.set_halign(Gtk.Align.END)

        bottom.pack_start(big_time, True, True, 0)   # kiri: jam besar
        bottom.pack_end(actions, False, False, 0)    # kanan: tombol

        content.pack_start(lbl_cat, False, False, 0)
        content.pack_start(lbl_sub, False, False, 0)
        content.pack_start(bottom, False, False, 0)

        # pasang konten persis di atas kartu
        content_box = Gtk.Overlay()
        content_box.add(card_img)
        content_box.add_overlay(content)

        # wrapper center
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrap.set_halign(Gtk.Align.CENTER)
        wrap.set_valign(Gtk.Align.CENTER)
        wrap.pack_start(content_box, False, False, 0)

        if bg:
            overlay.add_overlay(wrap)
        else:
            overlay.add(wrap)
        self.add(overlay)
        self.finish()


STYLES = {'kartu': ('Kartu', BreakOverlay),
          'digital': ('Digital', DigitalOverlay),
          'teks': ('Teks berjalan', MarqueeOverlay),
          'minimal': ('Minimal', MinimalOverlay)}
STYLE_ORDER = ['kartu', 'digital', 'teks', 'minimal']


def show_reminder(style, prayer, jam, city, snooze_cb=None):
    cls = STYLES.get(style, STYLES['kartu'])[1]
    return cls(prayer, jam, city, snooze_cb=snooze_cb)


# ---------- TRAY APP ----------

HARI = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
DAYFULL = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']


def player_cmd(path, volume):
    """Perintah pemutar audio yang tersedia. None kalau tak ada."""
    if shutil.which('ffplay'):
        return ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet',
                '-volume', str(volume), path]
    if path.lower().endswith('.mp3') and shutil.which('mpg123'):
        return ['mpg123', '-q', path]
    if shutil.which('paplay'):
        return ['paplay', path]
    if shutil.which('aplay'):
        return ['aplay', path]
    return None


def monthly_css(P):
    a = P['accent']
    return f"""
.jw-root {{ background: {P['bg']}; }}
.jw-root label {{ font-family: Inter, 'Inter Display', 'Segoe UI', Cantarell, sans-serif; }}
.jw-cap {{ color: {a}; font-size: 10px; font-weight: 800; letter-spacing: 2px; }}
.jw-title {{ color: {P['text']}; font-size: 25px; font-weight: 800; }}
.jw-sub {{ color: {P['muted']}; font-size: 11px; }}
.jw-topline {{ border-bottom: 1px solid {rgba(a, 0.22)}; padding-bottom: 13px; }}
.jw-nav {{ background: transparent; border: 1px solid {rgba(P['text'], 0.10)};
          border-radius: 999px; color: {P['text2']}; font-weight: 700;
          min-width: 28px; min-height: 28px; padding: 0; }}
.jw-nav:hover {{ border-color: {rgba(a, 0.55)}; color: {a}; }}
.jw-ghost {{ background: transparent; border: none; color: {P['muted']};
            font-weight: 700; padding: 6px 10px; }}
.jw-ghost:hover {{ color: {a}; }}
.jw-root treeview.view {{
    background: {P['bg']}; color: {P['text2']};
    font-family: Inter, 'Inter Display', 'Segoe UI', Cantarell, sans-serif;
    -GtkTreeView-grid-line-width: 0;
    -GtkTreeView-vertical-separator: 0;
    -GtkTreeView-horizontal-separator: 0; }}
.jw-root treeview.view:selected {{ background: {rgba(a, 0.14)}; color: {P['text']}; }}
.jw-root treeview header button {{
    background: transparent; border: none;
    border-bottom: 1px solid {rgba(P['text'], 0.08)};
    color: {P['faint']}; font-size: 10px; font-weight: 700; letter-spacing: 1px;
    padding: 7px 4px 9px 4px; }}
.jw-root treeview header button:hover {{ color: {P['sub']}; }}
"""


class MonthlyWindow(Gtk.Window):
    """Popup jadwal sholat 1 bulan penuh (bisa ganti bulan)."""

    # kolom model: 0=hari, 1=nama hari, 2..9=waktu, terakhir=flag hari ini
    COL_TODAY = len(ALL) + 2

    def __init__(self, cfg, place):
        super().__init__(title='Jadwal Sholat Bulanan')
        self.cfg, self.place = cfg, place
        now = datetime.now()
        self.year, self.month = now.year, now.month
        self.set_default_size(790, 610)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class('jw-root')
        prov = Gtk.CssProvider()
        self.P = palette(cfg)
        prov.load_from_data(monthly_css(self.P).encode())
        self.get_style_context().add_provider(
            prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_border_width(18)
        self.add(root)

        # --- header: judul + navigasi ---
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        head.get_style_context().add_class('jw-topline')
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cap = Gtk.Label(label='JADWAL SHOLAT', xalign=0)
        cap.get_style_context().add_class('jw-cap')
        self.lbl_title = Gtk.Label(xalign=0)
        self.lbl_title.get_style_context().add_class('jw-title')
        self.lbl_sub = Gtk.Label(xalign=0)
        self.lbl_sub.get_style_context().add_class('jw-sub')
        for w in (cap, self.lbl_title, self.lbl_sub):
            left.pack_start(w, False, False, 0)
        head.pack_start(left, True, True, 0)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav.set_valign(Gtk.Align.CENTER)
        b_this = Gtk.Button(label='Bulan ini')
        b_this.get_style_context().add_class('jw-ghost')
        b_this.connect('clicked', lambda *_: self.goto_today())
        b_prev = Gtk.Button(label='\u2039')
        b_prev.get_style_context().add_class('jw-nav')
        b_prev.set_tooltip_text('Bulan lalu')
        b_prev.connect('clicked', lambda *_: self.shift(-1))
        b_next = Gtk.Button(label='\u203a')
        b_next.get_style_context().add_class('jw-nav')
        b_next.set_tooltip_text('Bulan depan')
        b_next.connect('clicked', lambda *_: self.shift(1))
        for b in (b_this, b_prev, b_next):
            nav.pack_start(b, False, False, 0)
        head.pack_end(nav, False, False, 0)
        root.pack_start(head, False, False, 0)

        # --- tabel (TreeView: header & kolom dijamin sejajar) ---
        self.store = Gtk.ListStore(*([str] * (self.COL_TODAY + 1)))
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_enable_search(False)
        self.view.set_grid_lines(Gtk.TreeViewGridLines.NONE)

        drend = Gtk.CellRendererText()
        drend.set_property('ypad', 7)
        drend.set_property('xpad', 2)
        dcol = Gtk.TreeViewColumn('TANGGAL', drend)
        dcol.set_alignment(0.0)
        dcol.set_expand(True)
        dcol.set_cell_data_func(drend, self._cell_date)
        self.view.append_column(dcol)

        for i, name in enumerate(ALL):
            rend = Gtk.CellRendererText()
            rend.set_property('ypad', 7)
            rend.set_property('xalign', 0.5)
            col = Gtk.TreeViewColumn(name.upper(), rend, text=i + 2)
            col.set_alignment(0.5)
            col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            col.set_fixed_width(64)
            col.set_min_width(58)
            col.set_cell_data_func(rend, self._cell_time, i + 2)
            self.view.append_column(col)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_overlay_scrolling(True)
        sw.add(self.view)
        root.pack_start(sw, True, True, 0)

        self.connect('key-press-event', self.on_key)
        self.load()
        self.show_all()

    def on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
        return False

    def shift(self, d):
        m, y = self.month + d, self.year
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        self.month, self.year = m, y
        self.load()

    def goto_today(self):
        now = datetime.now()
        self.year, self.month = now.year, now.month
        self.load()

    def _cell_date(self, _col, cell, model, it, _data):
        P = self.P
        idx = model.get_path(it).get_indices()[0]
        today = model[it][self.COL_TODAY] == '1'
        dd, wd = model[it][0], model[it][1]
        if today:
            cell.set_property('markup',
                              f'<span size="14000" weight="800" '
                              f'foreground="{P["accent"]}">{dd}</span>  '
                              f'<span size="10500" foreground="{P["today_sub"]}">{wd}</span>')
            cell.set_property('background', P['today_bg'])
        else:
            cell.set_property('markup',
                              f'<span size="14000" weight="800" '
                              f'foreground="{P["text2"]}">{dd}</span>  '
                              f'<span size="10500" foreground="{P["muted"]}">{wd}</span>')
            cell.set_property('background', P['alt'] if idx % 2 else P['bg'])

    def _cell_time(self, _col, cell, model, it, time_idx):
        P = self.P
        idx = model.get_path(it).get_indices()[0]
        today = model[it][self.COL_TODAY] == '1'
        wajib = ALL[time_idx - 2] in WAJIB
        if today:
            cell.set_property('background', P['today_bg'])
            cell.set_property('foreground', P['today_text'] if wajib else P['today_sub'])
            cell.set_property('weight', 700)
        else:
            cell.set_property('background', P['alt'] if idx % 2 else P['bg'])
            cell.set_property('foreground', P['text2'] if wajib else P['faint'])
            cell.set_property('weight', 600 if wajib else 400)

    def load(self):
        src = self.cfg.get('SOURCE', 'aladhan')
        place = self.place.get('city_display') or self.place.get('city', '')
        self.lbl_title.set_text(f'{BULAN[self.month]} {self.year}')
        self.lbl_sub.set_text(f'{place.title()}  \u00b7  {src}')
        self.store.clear()

        today = date.today().isoformat()
        rows = fetch_month(self.cfg, self.place, self.year, self.month)
        today_idx = None
        for i, r in enumerate(rows):
            dt = datetime.strptime(r['iso'], '%Y-%m-%d')
            is_today = r.get('iso') == today
            if is_today:
                today_idx = i
            self.store.append([dt.strftime('%d'), DAYFULL[dt.weekday()]]
                              + [r.get(k, '--:--') for k in ALL]
                              + ['1' if is_today else ''])

        if today_idx is not None:
            def _scroll(i=today_idx):
                self.view.scroll_to_cell(
                    Gtk.TreePath.new_from_indices([i]), None, True, 0.0, 0.0)
                return False
            GLib.timeout_add(250, _scroll)


STATE = os.path.join(CACHE_DIR, 'state.json')
OMARCHY_PLUGIN = os.path.join(_XDG('XDG_CONFIG_HOME', '.config'), 'omarchy',
                              'plugins', 'ibeeng.sholat-tray')
SOURCES = {'aladhan': 'AlAdhan (koordinat/global)',
           'myquran': 'MyQuran (kota Indonesia)'}


def omarchy_widget_mode():
    """True kalau widget bar Omarchy terpasang di sesi Hyprland."""
    return bool(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
                and os.path.isdir(OMARCHY_PLUGIN))


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path)


class Tray:
    """Otak aplikasi: jadwal, notifikasi, adzan, layar pengingat.
    Ikon tray hanya tampil kalau TRAY=1, atau TRAY=auto di luar widget Omarchy."""

    def __init__(self, app):
        self.app = app
        self.cfg = load_conf()
        self.place = get_place(self.cfg)
        self.timings = fetch_timings(self.cfg, self.place)
        self.notified_for = set()
        self.shown_for = set()   # layar pengingat yg sudah tampil hari ini
        self.played_for = set()  # adzan yg sudah diputar hari ini
        self.snooze_until = {}   # prayer -> timestamp tunda
        self.playing = None      # proses pemutar adzan
        self.ind = None
        self.menu_building = False
        tray = (self.cfg.get('TRAY') or 'auto').lower()
        if tray == '1' or (tray == 'auto' and not omarchy_widget_mode()):
            self.ind = AppIndicator.Indicator.new(
                APP_ID, icon_name(),
                AppIndicator.IndicatorCategory.APPLICATION_STATUS)
            self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.ind.set_title(APP_NAME)
            self.build_menu()
        self.tick = 0
        self.update()
        GLib.timeout_add_seconds(30, self.update)

    # ----- menu tray (desktop tanpa widget Omarchy) -----
    def _radio_menu(self, label, items, current, on_pick):
        sub = Gtk.MenuItem(label=label)
        menu = Gtk.Menu()
        group = None
        for key, text in items:
            r = Gtk.RadioMenuItem(label=text)
            if group:
                r.join_group(group)
            group = group or r
            r.set_active(key == current)
            r.connect('toggled', lambda w, k=key: (
                w.get_active() and not self.menu_building and on_pick(k)))
            menu.append(r)
        sub.set_submenu(menu)
        return sub

    def build_menu(self):
        if not self.ind:
            return
        self.menu_building = True
        m = Gtk.Menu()
        self.info_items = {}
        for name in ALL:
            mi = Gtk.MenuItem(label='...')
            mi.set_sensitive(False)
            m.append(mi)
            self.info_items[name] = mi
        m.append(Gtk.SeparatorMenuItem())
        self.mi_hijri = Gtk.MenuItem(label='...')
        self.mi_hijri.set_sensitive(False)
        m.append(self.mi_hijri)
        self.mi_city = Gtk.MenuItem(label='...')
        self.mi_city.set_sensitive(False)
        m.append(self.mi_city)
        m.append(Gtk.SeparatorMenuItem())

        def item(label, cb):
            mi = Gtk.MenuItem(label=label)
            mi.connect('activate', lambda *_: cb())
            m.append(mi)
            return mi
        item('Jadwal bulanan', self.open_monthly)
        adz = Gtk.CheckMenuItem(label='Putar adzan otomatis')
        adz.set_active(self.cfg.get('ADZAN', '1') == '1')
        adz.connect('toggled', lambda w: not self.menu_building
                    and self.set_adzan(w.get_active()))
        m.append(adz)
        self.mi_stop = item('Hentikan adzan', self.stop_adzan)
        m.append(Gtk.SeparatorMenuItem())
        m.append(self._radio_menu(
            'Gaya pengingat', [(k, STYLES[k][0]) for k in STYLE_ORDER],
            self.style(), self.set_style))
        m.append(self._radio_menu(
            'Warna', [(k, THEME_LABEL_OMARCHY if k == 'omarchy'
                       else THEMES[k]['label']) for k in THEME_ORDER],
            self.color(), self.set_color))
        m.append(self._radio_menu(
            'Sumber jadwal', list(SOURCES.items()),
            self.cfg.get('SOURCE', 'aladhan').lower(), self.set_source))
        m.append(Gtk.SeparatorMenuItem())
        item('Tes layar pengingat', lambda: self.show_overlay('Maghrib', test=True))
        item('Tes adzan', lambda: self.play_adzan('Maghrib', force=True))
        item('Refresh + cek lokasi', self.refresh)
        item('Keluar', self.app.quit)
        m.show_all()
        self.menu = m
        self.ind.set_menu(m)
        self.menu_building = False

    # ----- pengaturan -----
    def style(self):
        v = (self.cfg.get('GAYA') or 'kartu').lower()
        return v if v in STYLES else 'kartu'

    def color(self):
        v = (self.cfg.get('TEMA') or 'omarchy').lower()
        return v if v in THEME_ORDER else 'omarchy'

    def _changed(self, rebuild=True):
        if rebuild:
            self.build_menu()
        self.update(check=False)

    def set_style(self, key):
        if key in STYLES:
            self.cfg['GAYA'] = key
            set_conf('GAYA', key)
            self._changed()

    def set_color(self, key):
        if key in THEME_ORDER:
            self.cfg['TEMA'] = key
            set_conf('TEMA', key)
            self._changed()

    def set_adzan(self, on):
        val = '1' if on else '0'
        self.cfg['ADZAN'] = val
        set_conf('ADZAN', val)
        if not on:
            self.stop_adzan()
        self._changed()

    def set_source(self, src):
        if src not in SOURCES or self.cfg.get('SOURCE') == src:
            return
        self.cfg['SOURCE'] = src
        set_conf('SOURCE', src)
        try:
            os.remove(CACHE)
        except OSError:
            pass
        self.timings = fetch_timings(self.cfg, self.place)
        self.notified_for.clear()
        self.shown_for.clear()
        self.played_for.clear()
        self._changed()

    def refresh(self):
        for f in (CACHE, LOCCACHE, HIJRI_CACHE):
            try:
                os.remove(f)
            except OSError:
                pass
        self.cfg = load_conf()
        self.place = get_place(self.cfg, force_geo=True)
        self.timings = fetch_timings(self.cfg, self.place)
        self.notified_for.clear()
        self._changed()

    def open_monthly(self):
        win = MonthlyWindow(self.cfg, self.place)
        win.present()

    # ----- perintah dari widget / CLI -----
    def command(self, args):
        """sholat-tray <perintah>: dipanggil widget bar atau terminal."""
        cmd, rest = args[0].lstrip('-'), args[1:]
        arg = rest[0].lower() if rest else ''
        if cmd in ('test-overlay', 'test'):
            prayer = rest[0] if rest and rest[0] in WAJIB else 'Maghrib'
            style = rest[1] if len(rest) > 1 and rest[1] in STYLES else None
            self.show_overlay(prayer, test=True, style=style)
        elif cmd == 'monthly':
            self.open_monthly()
        elif cmd == 'stop-adzan':
            self.stop_adzan()
        elif cmd == 'test-adzan':
            self.play_adzan('Maghrib', force=True)
        elif cmd == 'adzan':
            cur = self.cfg.get('ADZAN', '1') == '1'
            self.set_adzan({'on': True, 'off': False}.get(arg, not cur))
        elif cmd == 'style':
            self.set_style(arg)
        elif cmd == 'color':
            self.set_color(arg)
        elif cmd == 'source':
            self.set_source(arg)
        elif cmd == 'refresh':
            self.refresh()
        elif cmd == 'quit':
            self.app.quit()
        else:
            print(f'Perintah tidak dikenal: {args[0]}', file=sys.stderr)
            return 1
        return 0

    # ----- adzan -----
    def play_adzan(self, prayer, force=False):
        if not force and self.cfg.get('ADZAN', '1') != '1':
            return
        key = 'ADZAN_FAJR_FILE' if prayer == 'Subuh' else 'ADZAN_FILE'
        path = os.path.expanduser(self.cfg.get(key) or '')
        if not path or not os.path.exists(path):
            self.notify('File adzan tidak ditemukan',
                        f'Taruh file audio di {AUDIO_DIR} atau atur {key} di {CONF}')
            return
        try:
            vol = max(0, min(100, int(self.cfg.get('ADZAN_VOLUME', '80'))))
        except ValueError:
            vol = 80
        cmd = player_cmd(path, vol)
        if not cmd:
            self.notify('Tidak ada pemutar audio',
                        'Pasang ffmpeg (ffplay), mpg123, atau pulseaudio-utils')
            return
        self.stop_adzan()
        try:
            self.playing = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            GLib.timeout_add_seconds(2, self._watch_player)
        except Exception as e:
            print('gagal putar adzan:', e)
            self.playing = None
        self.write_state()

    def _watch_player(self):
        if self.playing and self.playing.poll() is None:
            return True
        self.playing = None
        self.write_state()
        return False

    def stop_adzan(self, *_):
        p = self.playing
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
        self.playing = None
        self.write_state()

    def notify(self, title, body):
        try:
            body = GLib.markup_escape_text(body)
            subprocess.Popen(['notify-send', title, body,
                              '-a', APP_NAME, '-i', icon_name(),
                              '-u', 'normal', '-t', '10000'])
        except Exception:
            pass

    def show_overlay(self, prayer, test=False, style=None):
        jam = self.timings.get(prayer, '--:--')
        city = self.place.get('city_display') or self.place.get('city', '')

        def snooze():
            if test:
                return
            self.snooze_until[prayer] = time.time() + 300
            self.shown_for.discard(f"{date.today().isoformat()}-{prayer}")
            GLib.timeout_add_seconds(301, self.update)
        show_reminder(style or self.style(), prayer, jam, city, snooze_cb=snooze)

    # ----- state untuk widget bar -----
    def write_state(self):
        base = _omarchy_base()
        colors = [{'id': 'omarchy', 'label': THEME_LABEL_OMARCHY,
                   'accent': base['accent'] if base else ''}]
        colors += [{'id': k, 'label': THEMES[k]['label'],
                    'accent': THEMES[k]['accent']} for k in THEME_ORDER[1:]]
        try:
            write_json_atomic(STATE, {
                'version': 1,
                'city': self.place.get('city_display') or self.place.get('city', ''),
                'hijri': hijri_today() or '',
                'source': self.cfg.get('SOURCE', 'aladhan'),
                'adzan': self.cfg.get('ADZAN', '1') == '1',
                'playing': bool(self.playing and self.playing.poll() is None),
                'style': self.style(),
                'color': self.color(),
                'styles': [{'id': k, 'label': STYLES[k][0]} for k in STYLE_ORDER],
                'colors': colors,
            })
        except Exception as e:
            print('tulis state gagal:', e)

    def update(self, check=True):
        self.tick += 1
        # refresh lokasi tiap ~30 menit (60 tick x 30 dtk)
        if self.tick % 60 == 0:
            self.place = get_place(self.cfg)
        self.timings = fetch_timings(self.cfg, self.place)
        city = self.place.get('city_display') or self.place.get('city', '?')
        name, jam = next_prayer(self.timings)
        sisa_mnt = minutes_to(jam)
        self.write_state()
        if self.ind:
            label = f' {name} {jam} ({countdown(jam)})'
            try:
                self.ind.set_label(label, label)
                self.ind.set_title(f'{APP_NAME}:{label}')
                for n in ALL:
                    mark = '▶ ' if n == name else '    '
                    self.info_items[n].set_label(
                        f"{mark}{n}: {self.timings.get(n, '--:--')}")
                auto = 'otomatis' if self.cfg.get('AUTO', '1') == '1' else 'manual'
                self.mi_city.set_label(f'Lokasi: {city} ({auto})')
                h = hijri_today()
                self.mi_hijri.set_label(f'Hijriah: {h}' if h else 'Hijriah: -')
            except Exception:
                pass
        if not check:
            return True
        today = date.today().isoformat()
        # H-10 menit: notifikasi biasa
        key10 = f'{today}-{name}-10'
        if sisa_mnt <= 10 and key10 not in self.notified_for:
            self.notified_for.add(key10)
            self.notify(f'Sebentar lagi {name} ({jam})',
                        f'{countdown(jam)} lagi — {city}. Bersiaplah untuk sholat.')
        # Masuk waktu: adzan + layar pengingat (sekali per sholat per hari)
        key0 = f'{today}-{name}'
        if name in WAJIB and sisa_mnt <= 0:
            if key0 not in self.played_for:
                self.played_for.add(key0)
                self.play_adzan(name)
            if (key0 not in self.shown_for
                    and time.time() > self.snooze_until.get(name, 0)):
                self.shown_for.add(key0)
                self.show_overlay(name)
        return True


class App(Gtk.Application):
    """Satu instance per sesi. Perintah berikutnya (`sholat-tray style
    digital`, dst.) diteruskan ke instance yang sedang berjalan."""

    def __init__(self):
        super().__init__(application_id='io.github.ibeeng.SholatTray',
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.tray = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # tetap hidup tanpa jendela

    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        if self.tray is None:
            self.tray = Tray(self)
        elif not args:
            cl.print_literal(f'{APP_NAME} sudah berjalan.\n')
        return self.tray.command(args) if args else 0


def preview(argv):
    """--preview GAYA [WARNA] [SHOLAT]: tampilkan layar pengingat sendirian
    (tanpa daemon), untuk mencoba gaya atau mengambil screenshot."""
    style = argv[0] if argv and argv[0] in STYLES else 'kartu'
    cfg = load_conf()
    if len(argv) > 1 and argv[1] in THEME_ORDER:
        os.environ['SHOLAT_TRAY_COLOR'] = argv[1]
    prayer = argv[2] if len(argv) > 2 and argv[2] in WAJIB else 'Maghrib'
    place = get_place(cfg)
    timings = fetch_timings(cfg, place)
    win = show_reminder(style, prayer, timings.get(prayer, '--:--'),
                        place.get('city_display') or place.get('city', ''),
                        snooze_cb=lambda: None)
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
    return 0


USAGE = """Pemakaian: sholat-tray [perintah]

  (tanpa perintah)          jalankan di latar (tray / widget bar)
  monthly                   buka jadwal bulanan
  test-overlay [SHOLAT] [GAYA]  coba layar pengingat
  style kartu|digital|teks|minimal
  color omarchy|senja|subuh|masjid|malam
  adzan on|off|toggle       putar adzan otomatis
  stop-adzan | test-adzan
  source aladhan|myquran
  refresh                   muat ulang jadwal + cek lokasi
  quit
  --preview GAYA [WARNA] [SHOLAT]   pratinjau tanpa daemon
  --version | --help
"""


def main(argv):
    migrate_legacy_conf()
    if len(argv) >= 2 and argv[1] in ('-v', '--version'):
        print(f'{APP_NAME} {VERSION}')
        return 0
    if len(argv) >= 2 and argv[1] in ('-h', '--help', 'help'):
        print(USAGE)
        return 0
    if len(argv) >= 2 and argv[1] == '--preview':
        return preview(argv[2:])
    return App().run(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
