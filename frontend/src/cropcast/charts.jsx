// Compact, dependency-free SVG charts for the Panchayat panel.
//
// Design rules (data integrity first):
//  * Every chart plots ONLY values present in the API payload. A missing / non-finite
//    value is skipped (the line breaks, the bar is absent) — nothing is interpolated.
//  * If fewer days than requested have data, the chart says so ("5 of 7 days").
//  * No axes or legends: faint reference lines and value labels on the marks, like a weather app.
//  * Missing days are drawn as an explicit dashed "no data" slot so a gap never looks like a bug.
import { coverage, dayLabel, extent, isNum, seriesOf, sum } from "./forecastModel";

const W = 320;
const GRID = 3; // faint reference lines per chart
const COLORS = { tmax: "#ea580c", tmin: "#4f8fd6", rain: "#0369a1", humidity: "#15803d", wind: "#6d28d9" };

const linear = (d0, d1, r0, r1) => {
  const span = d1 - d0 || 1;
  return (v) => r0 + ((v - d0) / span) * (r1 - r0);
};

function xs(n, padL = 16, padR = 16) {
  if (n <= 1) return [W / 2];
  const step = (W - padL - padR) / (n - 1);
  return Array.from({ length: n }, (_, i) => padL + i * step);
}

// Split [{x,y}|null,...] into continuous runs so gaps stay gaps.
function runsOf(points) {
  const out = [];
  let cur = [];
  points.forEach((p) => {
    if (p) cur.push(p);
    else if (cur.length) { out.push(cur); cur = []; }
  });
  if (cur.length) out.push(cur);
  return out;
}

const pathOf = (run) => run.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

function fmt(v, decimals = 0) {
  if (!isNum(v)) return "";
  return decimals === 0 ? String(Math.round(v)) : v.toFixed(decimals);
}

const isToday = (d, now) => dayLabel(d, now).isToday;

function XLabels({ dates, positions, y, now }) {
  return dates.map((d, i) => {
    const lab = dayLabel(d, now);
    return (
      <text key={`${d}-${i}`} x={positions[i]} y={y} textAnchor="middle" className={lab.isToday ? "cc-x cc-x-today" : "cc-x"}>
        {lab.short}
      </text>
    );
  });
}

function Grid({ top, bottom }) {
  return Array.from({ length: GRID }, (_, i) => {
    const y = top + ((bottom - top) * i) / (GRID - 1);
    return <line key={i} x1="10" x2={W - 10} y1={y} y2={y} className={i === GRID - 1 ? "cc-base" : "cc-grid"} />;
  });
}

// Dashed empty slot for a day with no value — visibly "no data", not a rendering fault.
function Gaps({ series, positions, top, bottom }) {
  return series.map((p, i) => p.value === null && (
    <g key={`gap${i}`} className="cc-gap">
      <line x1={positions[i]} x2={positions[i]} y1={top} y2={bottom} />
      <text x={positions[i]} y={(top + bottom) / 2} textAnchor="middle">n/a</text>
    </g>
  ));
}

// ── Shell shared by every chart ──────────────────────────────────────────────
export function ChartCard({ title, question, summary, accent, caption, children }) {
  return (
    <section className="cc-chart-card">
      <header className="cc-chart-head">
        <div><h4>{title}</h4>{question && <p className="cc-chart-q">{question}</p>}</div>
        {summary && <span className="cc-chart-sum" style={accent ? { color: accent } : undefined}>{summary}</span>}
      </header>
      {children}
      {caption && <p className="cc-chart-cap">{caption}</p>}
    </section>
  );
}

export function ChartSkeleton({ title }) {
  return (
    <section className="cc-chart-card" aria-busy="true" aria-label={`${title} loading`}>
      <header className="cc-chart-head"><div><h4>{title}</h4></div></header>
      <div className="cc-skel" style={{ height: 88 }} />
    </section>
  );
}

export function ChartEmpty({ title, message = "No data available for this metric." }) {
  return (
    <ChartCard title={title}>
      <div className="cc-chart-empty">{message}</div>
    </ChartCard>
  );
}

function partialCaption(series) {
  const c = coverage(series);
  return c.partial ? `Showing ${c.have} of ${c.total} days. Days without data are marked n/a, never estimated.` : null;
}

// ── Temperature: daily high/low band ─────────────────────────────────────────
export function TemperatureChart({ daily, now }) {
  const title = "Temperature";
  const hi = seriesOf(daily, "temperature_max_c");
  const lo = seriesOf(daily, "temperature_min_c");
  const all = [...hi, ...lo];
  const ext = extent(all);
  if (!daily?.length || !ext) return <ChartEmpty title={title} />;

  const H = 128, padT = 22, padB = 24;
  const px = xs(daily.length);
  const y = linear(Math.floor(ext.min) - 1, Math.ceil(ext.max) + 1, H - padB, padT);
  const P = (series) => series.map((p, i) => (p.value === null ? null : { x: px[i], y: y(p.value), v: p.value }));
  const ph = P(hi), pl = P(lo);

  // Band only where BOTH ends exist for consecutive days.
  const bands = runsOf(ph.map((p, i) => (p && pl[i] ? { top: p, bot: pl[i], x: p.x, y: 0 } : null))).filter((r) => r.length > 1);
  const bandPath = (r) =>
    `${r.map((p, i) => `${i ? "L" : "M"}${p.top.x.toFixed(1)} ${p.top.y.toFixed(1)}`).join(" ")} ` +
    `${[...r].reverse().map((p) => `L${p.bot.x.toFixed(1)} ${p.bot.y.toFixed(1)}`).join(" ")} Z`;

  const dates = daily.map((d) => d.date);
  const summary = `${fmt(ext.min)}° – ${fmt(ext.max)}°`;
  const label = `${daily.length}-day temperature. Highs ${hi.filter((p) => p.value !== null).map((p) => fmt(p.value)).join(", ")} degrees Celsius; lows ${lo.filter((p) => p.value !== null).map((p) => fmt(p.value)).join(", ")}.`;

  return (
    <ChartCard title={title} question="How will temperature change?" summary={summary} accent={COLORS.tmax} caption={partialCaption([...hi])}>
      <svg viewBox={`0 0 ${W} ${H}`} className="cc-svg" role="img" aria-label={label}>
        <defs>
          <linearGradient id="cc-band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={COLORS.tmax} stopOpacity="0.20" />
            <stop offset="1" stopColor={COLORS.tmin} stopOpacity="0.16" />
          </linearGradient>
        </defs>
        <Grid top={padT} bottom={H - padB} />
        <Gaps series={hi} positions={px} top={padT} bottom={H - padB} />
        {bands.map((r, i) => <path key={i} d={bandPath(r)} fill="url(#cc-band)" />)}
        {runsOf(ph).map((r, i) => <path key={`h${i}`} d={pathOf(r)} fill="none" stroke={COLORS.tmax} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />)}
        {runsOf(pl).map((r, i) => <path key={`l${i}`} d={pathOf(r)} fill="none" stroke={COLORS.tmin} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />)}
        {ph.map((p, i) => p && (
          <g key={`ph${i}`}>
            {isToday(dates[i], now)
              ? <circle cx={p.x} cy={p.y} r="4.2" fill={COLORS.tmax} stroke="#fff" strokeWidth="1.8" />
              : <circle cx={p.x} cy={p.y} r="2.2" fill="#fff" stroke={COLORS.tmax} strokeWidth="1.3" />}
            <text x={p.x} y={p.y - 9} textAnchor="middle" className={isToday(dates[i], now) ? "cc-val cc-val-now" : "cc-val"} fill={COLORS.tmax}>{fmt(p.v)}°</text>
          </g>
        ))}
        {pl.map((p, i) => p && (
          <g key={`pl${i}`}>
            <circle cx={p.x} cy={p.y} r="1.9" fill="#fff" stroke={COLORS.tmin} strokeWidth="1.2" />
            <text x={p.x} y={p.y + 14} textAnchor="middle" className="cc-val cc-val-lo" fill={COLORS.tmin}>{fmt(p.v)}°</text>
          </g>
        ))}
        <XLabels dates={dates} positions={px} y={H - 6} now={now} />
      </svg>
    </ChartCard>
  );
}

// ── Humidity: soft area line ─────────────────────────────────────────────────
export function HumidityChart({ daily, now }) {
  const title = "Humidity";
  const s = seriesOf(daily, "humidity_pct");
  const ext = extent(s);
  if (!daily?.length || !ext) return <ChartEmpty title={title} />;

  const H = 104, padT = 22, padB = 24;
  const px = xs(daily.length);
  const mid = (ext.min + ext.max) / 2;
  const half = Math.max((ext.max - ext.min) / 2, 6); // never magnify tiny wiggles into drama
  const y = linear(mid - half - 3, mid + half + 3, H - padB, padT);
  const pts = s.map((p, i) => (p.value === null ? null : { x: px[i], y: y(p.value), v: p.value }));
  const runs = runsOf(pts);
  const base = H - padB;
  const dates = daily.map((d) => d.date);
  const label = `${daily.length}-day average relative humidity, ${fmt(ext.min)} to ${fmt(ext.max)} percent.`;

  return (
    <ChartCard title="Humidity" question="How will humidity change?" summary={`${fmt(ext.min)}–${fmt(ext.max)}%`} accent={COLORS.humidity} caption={partialCaption(s)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="cc-svg" role="img" aria-label={label}>
        <defs>
          <linearGradient id="cc-hum" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={COLORS.humidity} stopOpacity="0.28" />
            <stop offset="1" stopColor={COLORS.humidity} stopOpacity="0" />
          </linearGradient>
        </defs>
        <Grid top={padT} bottom={base} />
        <Gaps series={s} positions={px} top={padT} bottom={base} />
        {runs.filter((r) => r.length > 1).map((r, i) => (
          <path key={`a${i}`} d={`${pathOf(r)} L${r[r.length - 1].x.toFixed(1)} ${base} L${r[0].x.toFixed(1)} ${base} Z`} fill="url(#cc-hum)" />
        ))}
        {runs.map((r, i) => <path key={`l${i}`} d={pathOf(r)} fill="none" stroke={COLORS.humidity} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />)}
        {pts.map((p, i) => p && (
          <g key={i}>
            {isToday(dates[i], now)
              ? <circle cx={p.x} cy={p.y} r="4.2" fill={COLORS.humidity} stroke="#fff" strokeWidth="1.8" />
              : <circle cx={p.x} cy={p.y} r="2.2" fill="#fff" stroke={COLORS.humidity} strokeWidth="1.3" />}
            <text x={p.x} y={p.y - 9} textAnchor="middle" className={isToday(dates[i], now) ? "cc-val cc-val-now" : "cc-val"} fill={COLORS.humidity}>{fmt(p.v)}</text>
          </g>
        ))}
        <XLabels dates={dates} positions={px} y={H - 6} now={now} />
      </svg>
    </ChartCard>
  );
}

// ── Bars: rainfall and wind ──────────────────────────────────────────────────
function BarsChart({ daily, now, seriesKey, color, decimals, minMax, title, question, summary, unitWord, ariaUnit }) {
  const s = seriesOf(daily, seriesKey);
  const ext = extent(s);
  if (!daily?.length || !ext) return <ChartEmpty title={title} />;

  const H = 104, padT = 20, padB = 24;
  const px = xs(daily.length, 22, 22);
  const slot = daily.length > 1 ? px[1] - px[0] : 60;
  const bw = Math.min(26, slot * 0.58);
  const y = linear(0, Math.max(ext.max, minMax), H - padB, padT);
  const dates = daily.map((d) => d.date);
  const label = `${daily.length}-day ${unitWord}. ${s.filter((p) => p.value !== null).map((p) => `${fmt(p.value, decimals)} ${ariaUnit}`).join(", ")}.`;

  return (
    <ChartCard title={title} question={question} summary={summary(s)} accent={color} caption={partialCaption(s)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="cc-svg" role="img" aria-label={label}>
        <Grid top={padT} bottom={H - padB} />
        <Gaps series={s} positions={px} top={padT} bottom={H - padB} />
        {s.map((p, i) => {
          if (p.value === null) return null;
          const top = y(p.value);
          const h = Math.max(H - padB - top, p.value > 0 ? 2 : 1.5);
          return (
            <g key={i}>
              <rect x={px[i] - bw / 2} y={H - padB - h} width={bw} height={h} rx={Math.min(5, bw / 2)}
                fill={color} opacity={p.value > 0 ? (isToday(dates[i], now) ? 1 : 0.78) : 0.25} />
              {p.value > 0 && (
                <text x={px[i]} y={H - padB - h - 5} textAnchor="middle" className={isToday(dates[i], now) ? "cc-val cc-val-now" : "cc-val"} fill={color}>{fmt(p.value, decimals)}</text>
              )}
            </g>
          );
        })}
        <XLabels dates={dates} positions={px} y={H - 6} now={now} />
      </svg>
    </ChartCard>
  );
}

export function RainfallChart({ daily, now }) {
  return (
    <BarsChart
      daily={daily} now={now} seriesKey="rainfall_mm" color={COLORS.rain} decimals={1} minMax={5}
      title="Rainfall" question="When is rain expected?" unitWord="rainfall totals" ariaUnit="millimetres"
      summary={(s) => (sum(s) === null ? null : sum(s) === 0 ? "No rain" : `${sum(s).toFixed(1)} mm total`)}
    />
  );
}

export function WindChart({ daily, now }) {
  return (
    <BarsChart
      daily={daily} now={now} seriesKey="wind_kmph" color={COLORS.wind} decimals={0} minMax={10}
      title="Wind" question="How will wind change? (daily maximum)" unitWord="maximum wind speeds" ariaUnit="kilometres per hour"
      summary={(s) => { const e = extent(s); return e ? `up to ${fmt(e.max)} km/h` : null; }}
    />
  );
}

// Used while the forecast is loading: the panel shows the same four slots as skeletons.
export function ChartSkeletons() {
  return (
    <>
      <ChartSkeleton title="Temperature" />
      <ChartSkeleton title="Rainfall" />
      <ChartSkeleton title="Humidity" />
    </>
  );
}
