.pragma library

var ORDER = ["Subuh", "Terbit", "Dzuhur", "Ashar", "Maghrib", "Isya"]
var ALL = ["Imsak", "Subuh", "Terbit", "Dhuha", "Dzuhur", "Ashar", "Maghrib", "Isya"]
var HM = /^([01]\d|2[0-3]):[0-5]\d$/

// Parse cache JSON written by ~/bin/sholat-tray.py. Bounded and validated.
function parse(text) {
  var out = { ok: false, city: "", timings: {} }
  if (!text || text.length > 4096) return out
  try {
    var d = JSON.parse(text)
    var t = d && d.timings
    if (!t || typeof t !== "object") return out
    for (var i = 0; i < ALL.length; i++) {
      var v = String(t[ALL[i]] || "").slice(0, 5)
      if (HM.test(v)) out.timings[ALL[i]] = v
    }
    out.city = String(d.city || "").slice(0, 48)
    out.ok = Object.keys(out.timings).length > 0
  } catch (e) {}
  return out
}

function minutesOf(hm) {
  return parseInt(hm.slice(0, 2), 10) * 60 + parseInt(hm.slice(3, 5), 10)
}

// Next prayer after `now` (Date). Wraps to tomorrow's Subuh after Isya.
function next(timings, now) {
  var cur = now.getHours() * 60 + now.getMinutes()
  var secs = now.getSeconds()
  for (var i = 0; i < ORDER.length; i++) {
    var hm = timings[ORDER[i]]
    if (hm && minutesOf(hm) > cur)
      return { name: ORDER[i], time: hm, mins: minutesOf(hm) - cur - (secs > 0 ? 1 : 0) }
  }
  var s = timings["Subuh"] || "04:30"
  return { name: "Subuh", time: s, mins: minutesOf(s) + 1440 - cur - (secs > 0 ? 1 : 0) }
}

function countdown(mins) {
  if (mins < 0) mins = 0
  var h = Math.floor(mins / 60), m = mins % 60
  return h > 0 ? h + "j" + (m < 10 ? "0" : "") + m + "m" : m + "m"
}

var ID = /^[a-z]{1,16}$/
var HEX = /^#[0-9a-fA-F]{6}$/

function _items(list, withAccent) {
  var out = []
  if (!Array.isArray(list)) return out
  for (var i = 0; i < list.length && i < 12; i++) {
    var it = list[i] || {}
    if (!ID.test(String(it.id))) continue
    var o = { id: String(it.id), label: String(it.label || it.id).slice(0, 40) }
    if (withAccent) o.accent = HEX.test(String(it.accent)) ? String(it.accent) : ""
    out.push(o)
  }
  return out
}

// Parse state.json written by sholat-tray (settings + adzan playing flag).
function parseState(text) {
  var out = { ok: false, city: "", hijri: "", adzan: true, playing: false,
              style: "", color: "", styles: [], colors: [] }
  if (!text || text.length > 16384) return out
  try {
    var d = JSON.parse(text)
    out.city = String(d.city || "").slice(0, 48)
    out.hijri = String(d.hijri || "").slice(0, 48)
    out.adzan = d.adzan !== false
    out.playing = d.playing === true
    out.style = ID.test(String(d.style)) ? String(d.style) : ""
    out.color = ID.test(String(d.color)) ? String(d.color) : ""
    out.styles = _items(d.styles, false)
    out.colors = _items(d.colors, true)
    out.ok = true
  } catch (e) {}
  return out
}

// Only ids that passed ID reach the shell command line.
function safeArg(v) { return ID.test(String(v)) ? String(v) : "" }
