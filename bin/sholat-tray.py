#!/usr/bin/env python3
"""Tray waktu sholat untuk XFCE panel (systray) - tanpa sudo.
- Lokasi OTOMATIS via IP geolocation (refresh tiap 30 mnt), fallback ke config.
- Sumber jadwal: Aladhan API by koordinat, method 20 = Kemenag Indonesia.
- Notif 10 mnt sebelum; FULLSCREEN overlay pas waktunya (bisa di-close/Esc).
- Test overlay: python3 ~/bin/sholat-tray.py --test-overlay Maghrib
Cache: ~/.cache/sholat-today.json + ~/.cache/sholat-lokasi.json
Config: ~/.config/sholat-kota.conf (AUTO=1/0, CITY=..., COUNTRY=..., METHOD=20)
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, date

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import Gtk, GLib, Gdk

HOME = os.path.expanduser('~')
CACHE = os.path.join(HOME, '.cache', 'sholat-today.json')
LOCCACHE = os.path.join(HOME, '.cache', 'sholat-lokasi.json')
CONF = os.path.join(HOME, '.config', 'sholat-kota.conf')

ORDER = ['Subuh', 'Terbit', 'Dzuhur', 'Ashar', 'Maghrib', 'Isya']
KEYMAP = {'Subuh': 'Fajr', 'Terbit': 'Sunrise', 'Dzuhur': 'Dhuhr',
          'Ashar': 'Asr', 'Maghrib': 'Maghrib', 'Isya': 'Isha'}
# overlay hanya untuk sholat wajib (bukan Terbit)
WAJIB = ['Subuh', 'Dzuhur', 'Ashar', 'Maghrib', 'Isya']


def load_conf():
    cfg = {'CITY': 'Jakarta', 'COUNTRY': 'Indonesia', 'METHOD': '20', 'AUTO': '1'}
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
        with urllib.request.urlopen(
                'http://ip-api.com/json/?fields=status,city,regionName,'
                'country,lat,lon,query', timeout=10) as r:
            d = json.load(r)
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


def fetch_timings(cfg, place):
    today = date.today().isoformat()
    cache_key = place.get('city')
    try:
        with open(CACHE) as f:
            c = json.load(f)
        if c.get('date') == today and c.get('city') == cache_key:
            return c['timings']
    except Exception:
        pass
    try:
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
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        t = data['data']['timings']
        timings = {id_: t[en].split()[0] for id_, en in KEYMAP.items()}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, 'w') as f:
            json.dump({'date': today, 'city': cache_key,
                       'timings': timings}, f)
        return timings
    except Exception:
        try:
            with open(CACHE) as f:
                return json.load(f)['timings']
        except Exception:
            return {'Subuh': '04:30', 'Terbit': '05:50', 'Dzuhur': '11:50',
                    'Ashar': '15:10', 'Maghrib': '18:00', 'Isya': '19:10'}


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


# ---------- FULLSCREEN OVERLAY (blur) ----------

BLUR_BG = '/tmp/sholat-blur-bg.png'


def grab_blur_bg(path=BLUR_BG, dark=0.55):
    """Screenshot desktop -> blur halus + gelapin. Return path / None."""
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


class BreakOverlay(Gtk.Window):
    """Layar penuh pengingat sholat: wallpaper ter-blur + kartu poster-style.
    Bisa di-close: tombol / Esc."""
    def __init__(self, prayer, jam, city, snooze_cb=None):
        super().__init__(title=f'Waktunya {prayer}')
        self.snooze_cb = snooze_cb
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

        css = (
            "#sholat-overlay { background: #050507; }"
            "#sholat-overlay * { font-family: Inter, 'Inter Display', 'Segoe UI', Cantarell, sans-serif; }"
            ".btn-gold { background: #f5c542; color: #111214; border: none;"
            " border-radius: 999px; font-weight: 900;"
            " box-shadow: 0 10px 40px rgba(245,197,66,0.35),"
            " 0 0 24px rgba(245,197,66,0.25); }"
            ".btn-gold:hover { background: #ffdb6b; }"
            ".btn-text { background: transparent; border: none; color: #8f8f98;"
            " font-weight: 700; }"
            ".btn-text:hover { color: #f5c542; }"
        )
        prov = Gtk.CssProvider()
        prov.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.connect('key-press-event', self.on_key)

        overlay = Gtk.Overlay()

        # --- LAYER 0: wallpaper blur (fullscreen) ---
        bg = grab_blur_bg()
        if bg:
            bg_img = Gtk.Image.new_from_file(bg)
            bg_img.set_hexpand(True)
            bg_img.set_vexpand(True)
            overlay.add(bg_img)

        # --- LAYER 1: kartu poster (sky banner + angled cut + body) ---
        card_img = Gtk.Image.new_from_file('/home/waalidperfume/.cache/sholat-card-bg.png')
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
        t1.set_markup('<span size="15000" weight="bold" color="#ffffff">WAKTU SHOLAT</span>')
        t1.set_halign(Gtk.Align.END)
        t2 = Gtk.Label()
        t2.set_markup('<span size="12000" color="#e8e8ee">Reminder Desktop</span>')
        t2.set_halign(Gtk.Align.END)
        line = Gtk.Label()
        line.set_markup('<span size="8000" color="#ffffff">──────────────</span>')
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
            f'<span size="23000" weight="bold" color="#ffffff">{prayer}</span>')
        lbl_cat.set_halign(Gtk.Align.START)
        lbl_cat.set_margin_start(48)
        lbl_cat.set_margin_bottom(4)
        lbl_sub = Gtk.Label()
        lbl_sub.set_markup(
            f'<span size="13500" color="#b9b9c2">{jam} \u2022 {city} \u2014 waktunya sholat, bro.</span>')
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
            f'<span size="48000" weight="heavy" color="#ffffff" letter_spacing="-500">{jam}</span>')
        big_time.set_valign(Gtk.Align.END)
        big_time.set_halign(Gtk.Align.START)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        actions.set_valign(Gtk.Align.END)
        actions.set_halign(Gtk.Align.END)
        btn_close = Gtk.Button(label='Lanjut kerja')
        btn_close.get_style_context().add_class('btn-gold')
        btn_close.set_size_request(170, 44)
        btn_close.connect('clicked', lambda *_: self.destroy())
        btn_snooze = Gtk.Button(label='Tunda 5 menit')
        btn_snooze.get_style_context().add_class('btn-text')
        btn_snooze.connect('clicked', self.on_snooze)
        actions.pack_start(btn_close, False, False, 0)
        actions.pack_start(btn_snooze, False, False, 0)

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
        # window pas ukuran kartu (bukan fullscreen) di tengah layar
        self.set_resizable(False)
        self.show_all()
        GLib.timeout_add_seconds(600, self.auto_close)

    def on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def on_snooze(self, _b):
        if self.snooze_cb:
            self.snooze_cb()
        self.destroy()

    def auto_close(self):
        try:
            self.destroy()
        except Exception:
            pass
        return False


# ---------- TRAY APP ----------

class Tray:
    def __init__(self):
        self.cfg = load_conf()
        self.place = get_place(self.cfg)
        self.timings = fetch_timings(self.cfg, self.place)
        self.notified_for = set()
        self.shown_for = set()   # overlay yg sudah tampil hari ini
        self.snooze_until = {}   # prayer -> timestamp tunda
        self.ind = AppIndicator.Indicator.new(
            'sholat-tray', 'preferences-system-time',
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title('Waktu Sholat')
        self.menu = Gtk.Menu()
        self.info_items = {}
        for name in ORDER:
            mi = Gtk.MenuItem(label='...')
            mi.set_sensitive(False)
            self.menu.append(mi)
            self.info_items[name] = mi
        self.menu.append(Gtk.SeparatorMenuItem())
        self.mi_city = Gtk.MenuItem(label='...')
        self.mi_city.set_sensitive(False)
        self.menu.append(self.mi_city)
        mi_ref = Gtk.MenuItem(label='Refresh + cek lokasi')
        mi_ref.connect('activate', self.on_refresh)
        self.menu.append(mi_ref)
        mi_test = Gtk.MenuItem(label='Tes layar pengingat')
        mi_test.connect('activate', lambda *_: self.show_overlay('Maghrib'))
        self.menu.append(mi_test)
        mi_web = Gtk.MenuItem(label='Jadwal lengkap (browser)')
        mi_web.connect('activate', self.on_web)
        self.menu.append(mi_web)
        mi_quit = Gtk.MenuItem(label='Keluar')
        mi_quit.connect('activate', Gtk.main_quit)
        self.menu.append(mi_quit)
        self.menu.show_all()
        self.ind.set_menu(self.menu)
        self.tick = 0
        self.update()
        GLib.timeout_add_seconds(30, self.update)

    def on_refresh(self, _w):
        for f in (CACHE, LOCCACHE):
            try:
                os.remove(f)
            except OSError:
                pass
        self.cfg = load_conf()
        self.place = get_place(self.cfg, force_geo=True)
        self.timings = fetch_timings(self.cfg, self.place)
        self.notified_for.clear()
        self.update()

    def on_web(self, _w):
        url = 'https://www.jadwalsholat.org/'
        subprocess.Popen(['xdg-open', url])

    def notify(self, title, body):
        try:
            subprocess.Popen(['notify-send', title, body,
                              '-i', 'preferences-system-time',
                              '-u', 'normal', '-t', '10000'])
        except Exception:
            pass

    def show_overlay(self, prayer):
        jam = self.timings.get(prayer, '--:--')
        city = self.place.get('city', '')
        def snooze():
            self.snooze_until[prayer] = time.time() + 300
            self.shown_for.discard(f"{date.today().isoformat()}-{prayer}")
            GLib.timeout_add_seconds(300, self.update)
        BreakOverlay(prayer, jam, city, snooze_cb=snooze)

    def update(self):
        self.tick += 1
        # refresh lokasi tiap ~30 menit (60 tick x 30 dtk)
        if self.tick % 60 == 0:
            self.place = get_place(self.cfg)
        self.timings = fetch_timings(self.cfg, self.place)
        city = self.place.get('city', '?')
        name, jam = next_prayer(self.timings)
        sisa_mnt = minutes_to(jam)
        label = f' {name} {jam} ({countdown(jam)})'
        try:
            self.ind.set_label(label, label)
        except Exception:
            pass
        for n in ORDER:
            mark = '▶ ' if n == name else '    '
            self.info_items[n].set_label(f"{mark}{n}: {self.timings.get(n, '--:--')}")
        try:
            auto = 'otomatis' if self.cfg.get('AUTO', '1') == '1' else 'manual'
            self.mi_city.set_label(f'Lokasi: {city} ({auto})')
        except Exception:
            pass
        today = date.today().isoformat()
        # H-10 menit: notif biasa
        key10 = f'{today}-{name}-10'
        if sisa_mnt <= 10 and key10 not in self.notified_for:
            self.notified_for.add(key10)
            self.notify(f'Sebentar lagi {name} ({jam})',
                        f'{countdown(jam)} lagi — {city}. Siap-siap sholat bro.')
        # Pas waktunya: fullscreen overlay (sekali per sholat per hari)
        key0 = f'{today}-{name}'
        if (name in WAJIB and sisa_mnt <= 0 and key0 not in self.shown_for
                and time.time() > self.snooze_until.get(name, 0)):
            self.shown_for.add(key0)
            self.show_overlay(name)
        return True


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--test-overlay':
        prayer = sys.argv[2] if len(sys.argv) > 2 else 'Maghrib'
        cfg = load_conf()
        place = get_place(cfg)
        timings = fetch_timings(cfg, place)
        BreakOverlay(prayer, timings.get(prayer, '--:--'),
                     place.get('city', ''), snooze_cb=lambda: None)
        Gtk.main()
    else:
        Tray()
        Gtk.main()
