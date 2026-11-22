#!/bin/bash
# Sholat Tray - XFCE Generic Monitor (xfce4-genmon-plugin), opsional.
# Membaca cache yang ditulis sholat-tray.
# Cara pakai: Add New Items -> Generic Monitor -> Command: sholat-tray-genmon, Period: 30
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/sholat-tray/today.json"

CITY=$(python3 -c "import json;print(json.load(open('$CACHE')).get('city','Jakarta'))" 2>/dev/null)
CITY=${CITY:-Jakarta}

if [ ! -f "$CACHE" ]; then
  sholat-tray >/dev/null 2>&1 &
  sleep 1
fi

NEXT=$(python3 -c "
import json
from datetime import datetime
try:
    t = json.load(open('$CACHE'))['timings']
except Exception:
    t = {}
now = datetime.now().strftime('%H:%M')
order = ['Subuh','Terbit','Dzuhur','Ashar','Maghrib','Isya']
for n in order:
    if t.get(n,'') > now:
        print(n, t[n]); break
else:
    print('Subuh', t.get('Subuh','--:--'))
" 2>/dev/null)

NAME=$(echo "$NEXT" | cut -d' ' -f1)
JAM=$(echo "$NEXT" | cut -d' ' -f2)

TIP=$(python3 -c "
import json
try:
    d = json.load(open('$CACHE'))
    t = d['timings']
    print('$CITY - ' + d.get('date',''))
    print('Subuh: '+t.get('Subuh','-')+' | Terbit: '+t.get('Terbit','-'))
    print('Dzuhur: '+t.get('Dzuhur','-')+' | Ashar: '+t.get('Ashar','-'))
    print('Maghrib: '+t.get('Maghrib','-')+' | Isya: '+t.get('Isya','-'))
except Exception as e:
    print('Jadwal sholat belum termuat')
" 2>/dev/null)

echo "<txt>🕌 $NAME $JAM</txt>"
echo "<tool>$TIP</tool>"
echo "<txtclick>xdg-open https://www.jadwalsholat.org >/dev/null 2>&1 &</txtclick>"
