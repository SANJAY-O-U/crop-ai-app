// Pure data helpers for the map-first CropCast UI. No React, no DOM, no network:
// every function turns the REAL API payloads (see backend/app/{weather,geospatial,
// downscaling}/schemas.py) into display-ready values, and returns null/"unavailable"
// instead of inventing anything when the payload does not contain it.
//
// What the API provides today (per Panchayat, per day):
//   temperature_min_c, temperature_max_c, rainfall_mm (daily sum),
//   humidity_pct (daily MEAN), wind_kmph (daily MAX)
// What it does NOT provide: current/hourly conditions, a weather description,
// crop risk, disease risk, or an advisory. See `insightsOf` for how those
// slots are handled.

export const EARTH_RADIUS_KM = 6371.0088;

export function haversineKm(lat1, lon1, lat2, lon2) {
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(lat2 - lat1);
  const dLon = rad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

export function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

// "2026-10-03" -> local Date (new Date("2026-10-03") would be UTC and can shift a day).
export function parseISODate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s ?? ""));
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function sameLocalDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// "Today" is only claimed when the forecast date equals the viewer's local date.
// The forecast's dates are LOCAL dates in the provider's timezone (backend: block_source.timezone, Asia/Kolkata for the
// pilot). "Today" must therefore be evaluated in that timezone, not in the viewer's. Returns a Date whose local
// year/month/day/hour equal the wall clock in `timeZone` (or `now` unchanged if the zone is missing/invalid).
export function nowInTimezone(timeZone, now = new Date()) {
  if (!timeZone) return now;
  try {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    }).formatToParts(now).filter((p) => p.type !== "literal").map((p) => [p.type, Number(p.value)]));
    return new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
  } catch {
    return now;
  }
}

export function dayLabel(dateStr, now = new Date()) {
  const d = parseISODate(dateStr);
  if (!d) return { short: "—", long: "—", isToday: false };
  const isToday = sameLocalDay(d, now);
  const wd = WEEKDAYS[d.getDay()];
  return {
    short: isToday ? "Today" : wd,
    initial: isToday ? "T" : wd[0],
    long: `${wd}, ${d.getDate()} ${MONTHS[d.getMonth()]}`,
    isToday,
  };
}

// [{ date, value }] with value === null when the field is missing or not finite.
export function seriesOf(daily, key) {
  return (daily ?? []).map((d) => ({ date: d?.date ?? null, value: isNum(d?.[key]) ? d[key] : null }));
}

export function coverage(series) {
  const have = series.filter((p) => p.value !== null).length;
  return { have, total: series.length, partial: have > 0 && have < series.length, empty: have === 0 };
}

export function extent(series) {
  const vals = series.map((p) => p.value).filter(isNum);
  if (!vals.length) return null;
  return { min: Math.min(...vals), max: Math.max(...vals) };
}

export function sum(series) {
  const vals = series.map((p) => p.value).filter(isNum);
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
}

// First forecast day, as plain numbers (or null). This is a DAILY FORECAST, not a
// "current reading" — callers should label it as today's forecast.
export function summarizeToday(forecast) {
  const d = forecast?.daily?.[0];
  if (!d) return null;
  const pick = (k) => (isNum(d[k]) ? d[k] : null);
  return {
    date: d.date ?? null,
    tmax: pick("temperature_max_c"),
    tmin: pick("temperature_min_c"),
    rain: pick("rainfall_mm"),
    humidity: pick("humidity_pct"),
    wind: pick("wind_kmph"),
  };
}

// Plain factual statements derived from the series. No thresholds, no risk
// language: "most rain on Thu" is a fact about the numbers, not advice.
export function highlights(forecast, now = new Date()) {
  const daily = forecast?.daily ?? [];
  const out = [];
  const best = (key, cmp) => {
    let idx = -1;
    daily.forEach((d, i) => {
      if (!isNum(d?.[key])) return;
      if (idx === -1 || cmp(d[key], daily[idx][key])) idx = i;
    });
    return idx;
  };

  const rainSeries = seriesOf(daily, "rainfall_mm");
  const rainTotal = sum(rainSeries);
  if (rainTotal !== null) {
    if (rainTotal === 0) {
      out.push({ id: "rain", kind: "dry", text: `No rain forecast in the next ${daily.length} days` });
    } else {
      const i = best("rainfall_mm", (a, b) => a > b);
      out.push({
        id: "rain", kind: "rain", value: daily[i].rainfall_mm, unit: "mm", day: dayLabel(daily[i].date, now),
        text: `Most rain: ${dayLabel(daily[i].date, now).short} · ${daily[i].rainfall_mm.toFixed(1)} mm`,
      });
    }
  }
  const hot = best("temperature_max_c", (a, b) => a > b);
  if (hot !== -1) {
    out.push({
      id: "heat", kind: "heat", value: daily[hot].temperature_max_c, unit: "°C", day: dayLabel(daily[hot].date, now),
      text: `Hottest: ${dayLabel(daily[hot].date, now).short} · ${daily[hot].temperature_max_c.toFixed(0)}°`,
    });
  }
  const wind = best("wind_kmph", (a, b) => a > b);
  if (wind !== -1) {
    out.push({
      id: "wind", kind: "wind", value: daily[wind].wind_kmph, unit: "km/h", day: dayLabel(daily[wind].date, now),
      text: `Windiest: ${dayLabel(daily[wind].date, now).short} · ${daily[wind].wind_kmph.toFixed(0)} km/h`,
    });
  }
  return out;
}

// Panchayat estimate minus the coarse block forecast, for the first day.
export function deltaVsBlock(forecast) {
  const p = forecast?.daily?.[0];
  const b = forecast?.block_source?.daily?.[0];
  if (!p || !b) return null;
  const d = (k) => (isNum(p[k]) && isNum(b[k]) ? p[k] - b[k] : null);
  const out = { tmax: d("temperature_max_c"), rain: d("rainfall_mm"), humidity: d("humidity_pct"), wind: d("wind_kmph") };
  return Object.values(out).every((v) => v === null) ? null : out;
}

// ── Slots the backend does not fill today ────────────────────────────────────
// Weather risk, crop risk, disease risk and an advisory are NOT produced by any
// current endpoint. They are read from an OPTIONAL `forecast.insights` object so
// the UI lights up automatically if the backend ever supplies it; until then every
// slot reports { available: false } and the UI shows an honest "not available".
// Expected future shape (a UI contract only — not an existing API):
//   insights: { weather_risk?: {level, label?}, crop_risk?: {...}, disease_risk?: {...},
//               advisory?: {title?, text} }
export function insightsOf(forecast) {
  const ins = forecast?.insights;
  const slot = (v) =>
    v && typeof v === "object" && (typeof v.level === "string" || typeof v.label === "string" || typeof v.text === "string")
      ? { available: true, ...v }
      : { available: false };
  return {
    weatherRisk: slot(ins?.weather_risk),
    cropRisk: slot(ins?.crop_risk),
    diseaseRisk: slot(ins?.disease_risk),
    advisory: slot(ins?.advisory),
    anyAvailable: Boolean(ins && (ins.weather_risk || ins.crop_risk || ins.disease_risk || ins.advisory)),
  };
}

export function nearestPanchayat(lat, lon, panchayats) {
  let best = null;
  for (const p of panchayats ?? []) {
    if (!isNum(p?.latitude) || !isNum(p?.longitude)) continue;
    const km = haversineKm(lat, lon, p.latitude, p.longitude);
    if (!best || km < best.km) best = { panchayat: p, km };
  }
  return best;
}

export function formatKm(km) {
  if (!isNum(km)) return "—";
  return km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km).toLocaleString("en-IN")} km`;
}

// Map-layer colour scales (low -> high). Variable identities match shared.jsx VARIABLES.
export const LAYER_SCALES = {
  rainfall_mm: ["#d7ecff", "#0369a1"],
  temperature_max_c: ["#fde9b8", "#c2410c"],
  humidity_pct: ["#dcf3e3", "#15803d"],
  wind_kmph: ["#e9e3ff", "#6d28d9"],
};

export function lerpHex(t, low, high) {
  const l = low.match(/\w\w/g).map((h) => parseInt(h, 16));
  const h = high.match(/\w\w/g).map((x) => parseInt(x, 16));
  return `rgb(${l.map((c, i) => Math.round(c + (h[i] - c) * t)).join(",")})`;
}

export function layerColor(value, min, max, scale) {
  if (!isNum(value)) return "#e5e7eb";
  if (!isNum(min) || !isNum(max) || max === min) return scale[1];
  return lerpHex(Math.min(1, Math.max(0, (value - min) / (max - min))), scale[0], scale[1]);
}

// Readable text colour (dark/light) for a given rgb()/hex background.
export function inkFor(bg) {
  const m = /rgb\((\d+),(\d+),(\d+)\)/.exec(bg);
  let r, g, b;
  if (m) [r, g, b] = [Number(m[1]), Number(m[2]), Number(m[3])];
  else {
    const hex = bg.replace("#", "");
    [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return L > 0.4 ? "#0f1a12" : "#ffffff";
}
