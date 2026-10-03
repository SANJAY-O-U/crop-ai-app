// Dependency-free tests (Node's built-in runner):  npm test
import test from "node:test";
import assert from "node:assert/strict";
import {
  coverage, deltaVsBlock, dayLabel, extent, formatKm, haversineKm, highlights, inkFor, insightsOf, layerColor,
  nearestPanchayat, parseISODate, seriesOf, summarizeToday, sum,
} from "./forecastModel.js";

const day = (date, o = {}) => ({
  date, temperature_min_c: 18, temperature_max_c: 30, rainfall_mm: 0, humidity_pct: 60, wind_kmph: 10, ...o,
});

test("parseISODate gives a LOCAL date (no UTC day shift)", () => {
  const d = parseISODate("2026-10-03");
  assert.deepEqual([d.getFullYear(), d.getMonth(), d.getDate()], [2026, 9, 3]);
  assert.equal(parseISODate("nonsense"), null);
  assert.equal(parseISODate(null), null);
});

test("dayLabel claims 'Today' only for the viewer's local date", () => {
  const now = new Date(2026, 9, 3, 15, 0);
  assert.equal(dayLabel("2026-10-03", now).short, "Today");
  assert.equal(dayLabel("2026-10-03", now).isToday, true);
  assert.equal(dayLabel("2026-10-04", now).short, "Sun");
  assert.equal(dayLabel("2026-10-04", now).long, "Sun, 4 Oct");
  assert.equal(dayLabel("2026-10-02", now).isToday, false);
  assert.equal(dayLabel("bad", now).short, "—");
});

test("seriesOf keeps positions and nulls missing / non-finite values (no filling)", () => {
  const s = seriesOf([day("2026-10-03"), day("2026-10-04", { rainfall_mm: null }), { date: "2026-10-05" }, day("2026-10-06", { rainfall_mm: NaN })], "rainfall_mm");
  assert.deepEqual(s.map((p) => p.value), [0, null, null, null]);
  assert.equal(s.length, 4);
  assert.deepEqual(coverage(s), { have: 1, total: 4, partial: true, empty: false });
  assert.equal(coverage(seriesOf([], "x")).empty, true);
  assert.equal(extent(s).max, 0);
  assert.equal(extent([{ value: null }]), null);
  assert.equal(sum([{ value: null }]), null);
});

test("summarizeToday reads only the first day and nulls bad fields", () => {
  const f = { daily: [day("2026-10-03", { temperature_max_c: 31.4, wind_kmph: undefined }), day("2026-10-04")] };
  const t = summarizeToday(f);
  assert.equal(t.tmax, 31.4);
  assert.equal(t.wind, null);
  assert.equal(t.date, "2026-10-03");
  assert.equal(summarizeToday({ daily: [] }), null);
  assert.equal(summarizeToday(null), null);
});

test("highlights are plain facts derived from the data", () => {
  const now = new Date(2026, 9, 3);
  const f = { daily: [day("2026-10-03"), day("2026-10-04", { rainfall_mm: 12.34, temperature_max_c: 34, wind_kmph: 22 }), day("2026-10-05", { rainfall_mm: 3 })] };
  const h = Object.fromEntries(highlights(f, now).map((x) => [x.id, x]));
  assert.equal(h.rain.text, "Most rain: Sun · 12.3 mm");
  assert.equal(h.heat.text, "Hottest: Sun · 34°");
  assert.equal(h.wind.text, "Windiest: Sun · 22 km/h");
  const dry = highlights({ daily: [day("2026-10-03"), day("2026-10-04")] }, now).find((x) => x.id === "rain");
  assert.equal(dry.kind, "dry");
  assert.equal(dry.text, "No rain forecast in the next 2 days");
  assert.deepEqual(highlights({ daily: [] }, now), []);
  assert.deepEqual(highlights(null, now), []);
});

test("highlights skip a metric whose values are all missing instead of guessing", () => {
  const f = { daily: [{ date: "2026-10-03", temperature_max_c: 30 }, { date: "2026-10-04", temperature_max_c: 32 }] };
  const ids = highlights(f).map((x) => x.id);
  assert.deepEqual(ids, ["heat"]);
});

test("deltaVsBlock is panchayat minus block for day one, null when unknowable", () => {
  const f = {
    daily: [day("2026-10-03", { temperature_max_c: 27, rainfall_mm: 4 })],
    block_source: { daily: [day("2026-10-03", { temperature_max_c: 30, rainfall_mm: 3 })] },
  };
  const d = deltaVsBlock(f);
  assert.equal(d.tmax, -3);
  assert.equal(d.rain, 1);
  assert.equal(deltaVsBlock({ daily: f.daily }), null);
});

test("insightsOf: crop risk, disease risk and advisory are UNAVAILABLE unless the API supplies them", () => {
  const none = insightsOf({ daily: [day("2026-10-03")] });
  assert.deepEqual([none.weatherRisk, none.cropRisk, none.diseaseRisk, none.advisory].map((s) => s.available), [false, false, false, false]);
  assert.equal(none.anyAvailable, false);
  assert.equal(insightsOf(null).cropRisk.available, false);
  const some = insightsOf({ insights: { crop_risk: { level: "Low" }, advisory: { text: "Irrigate in the evening." } } });
  assert.equal(some.cropRisk.available, true);
  assert.equal(some.cropRisk.level, "Low");
  assert.equal(some.advisory.text, "Irrigate in the evening.");
  assert.equal(some.diseaseRisk.available, false);
  assert.equal(insightsOf({ insights: { crop_risk: "high" } }).cropRisk.available, false); // malformed -> unavailable
});

test("haversine + nearestPanchayat", () => {
  assert.ok(Math.abs(haversineKm(12.0, 77.0, 12.0, 77.1) - 10.87) < 0.1);
  assert.equal(haversineKm(10, 10, 10, 10), 0);
  const ps = [
    { panchayat_id: "A", latitude: 13.37, longitude: 77.68 },
    { panchayat_id: "B", latitude: 13.47, longitude: 77.5 },
    { panchayat_id: "bad", latitude: null, longitude: 77 },
  ];
  const n = nearestPanchayat(13.46, 77.51, ps);
  assert.equal(n.panchayat.panchayat_id, "B");
  assert.ok(n.km < 3);
  assert.equal(nearestPanchayat(1, 1, []), null);
  assert.equal(formatKm(3.14159), "3.1 km");
  assert.equal(formatKm(412.4), "412 km");
  assert.equal(formatKm(null), "—");
});

test("layer colours: bounded, safe on degenerate ranges, readable ink", () => {
  const scale = ["#000000", "#ffffff"];
  assert.equal(layerColor(0, 0, 10, scale), "rgb(0,0,0)");
  assert.equal(layerColor(10, 0, 10, scale), "rgb(255,255,255)");
  assert.equal(layerColor(99, 0, 10, scale), "rgb(255,255,255)"); // clamped
  assert.equal(layerColor(5, 3, 3, scale), "#ffffff"); // min === max
  assert.equal(layerColor(null, 0, 10, scale), "#e5e7eb");
  assert.equal(inkFor("rgb(255,255,255)"), "#0f1a12");
  assert.equal(inkFor("rgb(0,0,0)"), "#ffffff");
  assert.equal(inkFor("#c2410c"), "#ffffff");
});
