// Sholat Tray, halaman proyek. Tanpa dependensi.
'use strict';

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const SVGNS = 'http://www.w3.org/2000/svg';

/* ---------- 7-segmen (geometri sama dengan gaya Digital di app) ---------- */
const SEG7 = { 0: 'abcdef', 1: 'bc', 2: 'abged', 3: 'abgcd', 4: 'fgbc',
  5: 'afgcd', 6: 'afgedc', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg' };

function segPolys(x, y, w, h, t) {
  const g = t * 0.16;
  const x0 = x + t / 2 + g, x1 = x + w - t / 2 - g;
  const hseg = (c) => [[x0, c], [x0 + t / 2, c - t / 2], [x1 - t / 2, c - t / 2],
    [x1, c], [x1 - t / 2, c + t / 2], [x0 + t / 2, c + t / 2]];
  const vseg = (cx, y0, y1) => [[cx, y0], [cx + t / 2, y0 + t / 2], [cx + t / 2, y1 - t / 2],
    [cx, y1], [cx - t / 2, y1 - t / 2], [cx - t / 2, y0 + t / 2]];
  const lx = x + t / 2, rx = x + w - t / 2;
  const up0 = y + t / 2 + g, up1 = y + h / 2 - g, lo0 = y + h / 2 + g, lo1 = y + h - t / 2 - g;
  return { a: hseg(y + t / 2), g: hseg(y + h / 2), d: hseg(y + h - t / 2),
    f: vseg(lx, up0, up1), b: vseg(rx, up0, up1), e: vseg(lx, lo0, lo1), c: vseg(rx, lo0, lo1) };
}

// Gambar teks seperti "17:24" (+ detik kecil opsional) ke dalam <svg>.
function drawSeg(svg, text, opts = {}) {
  const dh = 100, dw = dh * 0.54, t = dh * 0.12, gap = dw * 0.26, colonW = t * 2.4;
  const small = opts.small || '';
  const sh = dh * 0.38, sw = sh * 0.54, sgap = sw * 0.26;
  let width = 0;
  for (const ch of text) width += (ch === ':' ? colonW : dw) + gap;
  width -= gap;
  let total = width;
  if (small) total += dh * 0.16 + small.length * (sw + sgap) - sgap;
  const pad = 8;
  svg.setAttribute('viewBox', `${-pad} ${-pad} ${total + pad * 2 + 8} ${dh + pad * 2}`);
  svg.replaceChildren();
  const root = document.createElementNS(SVGNS, 'g');
  root.setAttribute('transform', `skewX(-4)`);
  svg.appendChild(root);

  const digit = (ch, x, y, h) => {
    const w = h * 0.54, tt = h * 0.12;
    const lit = SEG7[ch] || '';
    for (const [name, pts] of Object.entries(segPolys(x, y, w, h, tt))) {
      const p = document.createElementNS(SVGNS, 'polygon');
      p.setAttribute('points', pts.map((q) => q.map((n) => n.toFixed(2)).join(',')).join(' '));
      p.setAttribute('class', lit.includes(name) ? 'on' : 'off');
      root.appendChild(p);
    }
  };
  let cx = 0;
  for (const ch of text) {
    if (ch === ':') {
      for (const fy of [0.32, 0.68]) {
        const r = document.createElementNS(SVGNS, 'rect');
        r.setAttribute('x', cx + colonW / 2 - t / 2);
        r.setAttribute('y', dh * fy - t / 2);
        r.setAttribute('width', t);
        r.setAttribute('height', t);
        r.setAttribute('class', 'on colon' + (opts.colonOff ? ' dim' : ''));
        root.appendChild(r);
      }
      cx += colonW + gap;
      continue;
    }
    digit(ch, cx, 0, dh);
    cx += dw + gap;
  }
  if (small) {
    let sx = width + dh * 0.16;
    for (const ch of small) { digit(ch, sx, dh - sh, sh); sx += sw + sgap; }
  }
}

/* ---------- jam hero ---------- */
const clock = document.getElementById('clock');
let lastLabel = '';
function tickClock() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  drawSeg(clock, `${hh}:${mm}`, { small: ss, colonOff: !reduceMotion.matches && now.getSeconds() % 2 === 1 });
  const label = `Jam di perangkatmu: ${hh}.${mm}`;
  if (label !== lastLabel) { clock.setAttribute('aria-label', label); lastLabel = label; }
}
tickClock();
setInterval(tickClock, 1000);

/* ---------- papan teks berjalan: tombol jeda (R-39, gerak > 5 detik) ---------- */
const board = document.querySelector('.board');
const pauseBtn = document.getElementById('board-pause');
pauseBtn.addEventListener('click', () => {
  const paused = board.classList.toggle('paused');
  pauseBtn.setAttribute('aria-pressed', String(paused));
  pauseBtn.textContent = paused ? 'Putar' : 'Jeda';
});

/* ---------- tablist generik: klik, panah, Home/End ---------- */
function setupTabs(list) {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const select = (tab, focus = true) => {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
    }
    if (focus) tab.focus();
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => select(tab, false));
    tab.addEventListener('keydown', (e) => {
      const keys = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1 };
      if (!(e.key in keys)) return;
      e.preventDefault();
      select(tabs[(keys[e.key] + tabs.length) % tabs.length]);
    });
  });
  return (id) => { const t = tabs.find((x) => x.id === id); if (t) select(t, false); };
}
document.querySelectorAll('[role="tablist"]:not(.tablist)').forEach(setupTabs);
const selectStyle = setupTabs(document.querySelector('.tablist'));

// Tautan "Digital" di bawah jam membuka tab gaya yang sesuai.
document.querySelectorAll('a[data-tab]').forEach((a) => {
  a.addEventListener('click', () => selectStyle('tab-' + a.dataset.tab));
});

/* ---------- tombol salin ---------- */
const copyStatus = document.getElementById('copy-status');
document.querySelectorAll('.copy').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const text = btn.parentElement.querySelector('code').textContent;
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = 'Tersalin';
      copyStatus.textContent = 'Perintah disalin ke clipboard.';
    } catch {
      btn.textContent = 'Gagal';
      copyStatus.textContent = 'Tidak bisa menyalin. Pilih teksnya lalu salin manual.';
    }
    setTimeout(() => { btn.textContent = 'Salin'; }, 1800);
  });
});

/* ---------- cek jadwal kotamu (AlAdhan, metode 20 = Kemenag RI) ---------- */
const ORDER = [['Imsak', 'Imsak'], ['Subuh', 'Fajr'], ['Terbit', 'Sunrise'], ['Dzuhur', 'Dhuhr'],
  ['Ashar', 'Asr'], ['Maghrib', 'Maghrib'], ['Isya', 'Isha']];
const WAJIB = ['Subuh', 'Dzuhur', 'Ashar', 'Maghrib', 'Isya'];
const HM = /^([01]\d|2[0-3]):[0-5]\d$/;
const form = document.getElementById('check-form');
const out = document.getElementById('check-out');
const btn = document.getElementById('check-btn');
let countdownTimer = null;

function stateMsg(kind, text) {
  clearInterval(countdownTimer);
  const p = document.createElement('p');
  p.className = `state state-${kind}`;
  p.textContent = text;
  out.replaceChildren(p);
}

// Jam & menit sekarang di zona waktu kota (bukan zona waktu pengunjung).
function nowIn(tz) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date());
  const get = (k) => Number(parts.find((p) => p.type === k).value);
  return get('hour') * 3600 + get('minute') * 60 + get('second');
}
const toSec = (hm) => Number(hm.slice(0, 2)) * 3600 + Number(hm.slice(3, 5)) * 60;

function renderResult(city, times, tz, hijri) {
  const wrap = document.createElement('div');
  wrap.className = 'result';
  const left = document.createElement('div');
  left.className = 'result-next';
  const cap = document.createElement('p');
  const name = document.createElement('p');
  name.className = 'r-name';
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'seg');
  svg.setAttribute('role', 'img');
  const meta = document.createElement('p');
  meta.className = 'r-meta';
  meta.textContent = `${city} · ${tz}${hijri ? ' · ' + hijri : ''}`;
  left.append(cap, name, svg, meta);

  const list = document.createElement('ul');
  list.className = 'r-times';
  const rows = {};
  for (const [label] of ORDER) {
    if (!times[label]) continue;
    const li = document.createElement('li');
    if (!WAJIB.includes(label)) li.classList.add('minor');
    const a = document.createElement('span'); a.textContent = label;
    const b = document.createElement('span'); b.textContent = times[label];
    li.append(a, b);
    list.appendChild(li);
    rows[label] = li;
  }
  wrap.append(left, list);
  out.replaceChildren(wrap);

  const update = () => {
    const now = nowIn(tz);
    let next = WAJIB.find((n) => times[n] && toSec(times[n]) > now);
    let diff;
    if (next) diff = toSec(times[next]) - now;
    else { next = 'Subuh'; diff = toSec(times.Subuh) + 86400 - now; }
    for (const [n, li] of Object.entries(rows)) li.classList.toggle('next', n === next);
    cap.textContent = 'Sholat berikutnya';
    name.textContent = `${next} · ${times[next]}`;
    const h = Math.floor(diff / 3600), m = Math.floor((diff % 3600) / 60), s = diff % 60;
    const hm = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    drawSeg(svg, hm, { small: String(s).padStart(2, '0') });
    svg.setAttribute('aria-label', `Sisa waktu ${h} jam ${m} menit`);
  };
  update();
  countdownTimer = setInterval(update, 1000);
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const city = form.kota.value.trim().slice(0, 60);
  const country = form.negara.value.trim().slice(0, 60) || 'Indonesia';
  if (!city) {
    stateMsg('error', 'Nama kota masih kosong. Isi dulu, misalnya Bandung atau Makassar.');
    form.kota.focus();
    return;
  }
  stateMsg('loading', `Mengambil jadwal ${city} dari AlAdhan`);
  btn.disabled = true;
  try {
    const q = new URLSearchParams({ city, country, method: '20' });
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12000);
    const res = await fetch(`https://api.aladhan.com/v1/timingsByCity?${q}`, { signal: ctrl.signal });
    clearTimeout(timer);
    const data = await res.json().catch(() => null);
    if (!res.ok || !data || data.code !== 200) {
      stateMsg('error', `Kota "${city}" tidak ditemukan di ${country}. Coba ejaan lain atau nama kota terdekat.`);
      return;
    }
    const t = data.data.timings || {};
    const times = {};
    for (const [label, key] of ORDER) {
      const v = String(t[key] || '').slice(0, 5);
      if (HM.test(v)) times[label] = v;
    }
    const tz = String(data.data.meta && data.data.meta.timezone || '');
    let zone = 'UTC';
    try { new Intl.DateTimeFormat('en', { timeZone: tz }); zone = tz; } catch { /* zona tidak dikenal: pakai UTC */ }
    const h = data.data.date && data.data.date.hijri;
    const hijri = h ? `${h.day} ${h.month.en} ${h.year} H` : '';
    if (!times.Subuh) { stateMsg('error', 'Jadwal untuk kota ini tidak lengkap. Coba kota lain.'); return; }
    renderResult(city.charAt(0).toUpperCase() + city.slice(1), times, zone, hijri);
  } catch (err) {
    stateMsg('error', err.name === 'AbortError'
      ? 'AlAdhan tidak menjawab dalam 12 detik. Periksa koneksi, lalu coba lagi.'
      : 'Tidak bisa menghubungi api.aladhan.com. Periksa koneksi atau pemblokir konten, lalu coba lagi.');
  } finally {
    btn.disabled = false;
  }
});
