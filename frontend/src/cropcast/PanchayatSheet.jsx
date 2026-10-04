import { useRef, useState } from "react";
import { ChartSkeletons, HumidityChart, RainfallChart, TemperatureChart, WindChart } from "./charts";
import { dayLabel, deltaVsBlock, formatKm, highlights, insightsOf, isNum, nowInTimezone, summarizeToday } from "./forecastModel";
import { IconAlert, IconChevronDown, IconChevronUp, IconClose, IconCompare, IconDrops, IconInfo, IconLeaf, IconPin, IconRain, IconRefresh, IconSun, IconTable, IconWind } from "./icons";

const dash = "—";
const n0 = (v) => (isNum(v) ? String(Math.round(v)) : dash);
const n1 = (v) => (isNum(v) ? v.toFixed(1) : dash);
const signed = (v, d = 1) => (isNum(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}` : dash);

function Chip({ tone = "neutral", icon, children, title }) {
  return (
    <span className={`cc-chip cc-chip-${tone}`} title={title}>
      {icon}
      {children}
    </span>
  );
}

function Stat({ icon, label, value, unit }) {
  return (
    <div className="cc-stat">
      <span className="cc-stat-ico" aria-hidden="true">{icon}</span>
      <span className="cc-stat-val">{value}<small>{value === dash ? "" : unit}</small></span>
      <span className="cc-stat-lab">{label}</span>
    </div>
  );
}

const HIGHLIGHT_ICON = { rain: <IconRain width={15} height={15} />, dry: <IconSun width={15} height={15} />, heat: <IconSun width={15} height={15} />, wind: <IconWind width={15} height={15} /> };

function SheetSkeleton() {
  return (
    <div className="cc-sheet-pad" aria-busy="true" aria-label="Loading Panchayat forecast">
      <div className="cc-skel" style={{ height: 22, width: "55%", marginBottom: 10 }} />
      <div className="cc-skel" style={{ height: 14, width: "35%", marginBottom: 18 }} />
      <div className="cc-skel" style={{ height: 56, width: "42%", marginBottom: 16 }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
        {[0, 1, 2].map((i) => <div key={i} className="cc-skel" style={{ height: 62 }} />)}
      </div>
    </div>
  );
}

function Unavailable({ children }) {
  return <div className="cc-unavail"><IconInfo width={16} height={16} /><span>{children}</span></div>;
}

function RiskAndAdvisory({ insights, onOpenCropHealth }) {
  const slots = [
    ["Weather risk", insights.weatherRisk],
    ["Crop risk", insights.cropRisk],
    ["Disease risk", insights.diseaseRisk],
  ];
  return (
    <section className="cc-section" aria-labelledby="cc-risk-h">
      <h3 id="cc-risk-h" className="cc-section-h">Crop &amp; disease intelligence</h3>
      {insights.anyAvailable ? (
        <>
          <div className="cc-risk-row">
            {slots.map(([label, s]) => (
              <div key={label} className={`cc-risk ${s.available ? "" : "is-off"}`}>
                <span className="cc-risk-lab">{label}</span>
                <span className="cc-risk-val">{s.available ? (s.label ?? s.level) : "n/a"}</span>
              </div>
            ))}
          </div>
          {insights.advisory.available && (
            <div className="cc-advisory">
              <span className="cc-eyebrow">Recommended action</span>
              {insights.advisory.title && <strong>{insights.advisory.title}</strong>}
              <p>{insights.advisory.text}</p>
            </div>
          )}
        </>
      ) : (
        <div className="cc-future">
          <ul className="cc-future-list">
            {["Crop risk", "Disease risk", "Crop health", "Advisory", "Current conditions"].map((l) => (
              <li key={l}><span>{l}</span><em>Not available from current data source</em></li>
            ))}
          </ul>
          <p className="cc-future-note"><IconInfo width={14} height={14} />Reserved for a future intelligence layer. Nothing here is estimated or inferred from the forecast.</p>
          {onOpenCropHealth && (
            <button type="button" className="cc-link-btn" onClick={onOpenCropHealth}>
              <IconLeaf width={16} height={16} /> Check a crop photo for disease →
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function Compare({ forecast }) {
  const d = deltaVsBlock(forecast);
  const bs = forecast?.block_source;
  if (!d) return null;
  const rows = [
    ["High temperature", d.tmax, "°", 1],
    ["Rainfall", d.rain, " mm", 1],
    ["Humidity", d.humidity, " pts", 0],
    ["Wind", d.wind, " km/h", 0],
  ].filter(([, v]) => v !== null);
  return (
    <section className="cc-section" aria-labelledby="cc-cmp-h">
      <h3 id="cc-cmp-h" className="cc-section-h">Compared with the block forecast</h3>
      <p className="cc-section-sub">This Panchayat's first-day estimate minus the coarse block forecast it was derived from{bs?.source ? ` (${bs.source})` : ""}.</p>
      <dl className="cc-delta">
        {rows.map(([label, v, unit, dec]) => (
          <div key={label}><dt>{label}</dt><dd>{signed(v, dec)}{unit}</dd></div>
        ))}
      </dl>
    </section>
  );
}

function Method({ forecast }) {
  const a = forecast?.adjustment;
  if (!a) return null;
  return (
    <details className="cc-details">
      <summary>How this estimate is made</summary>
      {a.elevation_delta_m === null || a.elevation_delta_m === undefined ? (
        <p className="cc-note">{a.note ?? "Elevation data was unavailable, so no adjustment was applied."}</p>
      ) : (
        <>
          <p className="cc-note">
            This Panchayat sits <strong>{signed(a.elevation_delta_m, 0)} m</strong> relative to the block ({a.panchayat_elevation_m} m vs {a.block_elevation_m} m).
            Temperature uses the standard atmospheric lapse rate ({a.temperature_lapse_rate_c_per_m} °C per metre).
          </p>
          <p className="cc-note cc-note-warn">
            Rainfall, humidity and wind use placeholder heuristic coefficients that are <strong>not calibrated</strong> against observations yet.
          </p>
        </>
      )}
    </details>
  );
}

export default function PanchayatSheet({
  mode, expanded, onToggleExpanded, onClose, panchayat, forecast, block, loading, error, onRetry,
  onNavigate, onOpenCropHealth, sheetRef, summaryRef, userDistanceKm,
}) {
  const drag = useRef(null);
  const [dy, setDy] = useState(0);
  const isSheet = mode === "sheet";

  const onPointerDown = (e) => {
    if (!isSheet) return;
    drag.current = { y: e.clientY, moved: false };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    const delta = e.clientY - drag.current.y;
    if (Math.abs(delta) > 6) drag.current.moved = true;
    setDy(Math.max(0, delta));
  };
  const onPointerUp = (e) => {
    if (!drag.current) return;
    const delta = e.clientY - drag.current.y;
    const moved = drag.current.moved;
    drag.current = null;
    setDy(0);
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    if (!moved) return onToggleExpanded(); // a tap toggles
    if (delta < -40 && !expanded) onToggleExpanded();
    else if (delta > 40 && expanded) onToggleExpanded();
    else if (delta > 80 && !expanded) onClose();
  };

  const now = nowInTimezone(forecast?.block_source?.timezone);   // "Today" in the forecast's own timezone
  const today = summarizeToday(forecast);
  const lab = today ? dayLabel(today.date, now) : null;
  const insights = insightsOf(forecast);
  const facts = highlights(forecast, now).slice(0, 3);
  const daily = forecast?.daily ?? [];
  const isMocked = forecast?.block_source?.is_mocked;
  const name = panchayat?.panchayat_name ?? forecast?.panchayat_name ?? "Panchayat";

  return (
    <section
      ref={sheetRef}
      className={`cc-sheet cc-sheet-${mode} ${expanded ? "is-expanded" : "is-peek"}`}
      style={dy ? { transform: `translateY(${dy}px)`, transition: "none" } : undefined}
      aria-label={`${name} details`}
    >
      {isSheet && (
        <button
          type="button" className="cc-handle" aria-expanded={expanded} aria-controls="cc-sheet-more"
          aria-label={expanded ? "Collapse details" : "Expand details"}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
          onPointerCancel={() => { drag.current = null; setDy(0); }}
          onClick={(e) => { if (e.detail === 0) onToggleExpanded(); }} // keyboard / assistive-tech activation; pointer taps are handled on pointerup
        >
          <span aria-hidden="true" />
        </button>
      )}

      <div ref={summaryRef} className="cc-sheet-summary">
        <div className="cc-sheet-top">
          <div className="cc-crumb">
            <IconPin width={14} height={14} />
            <span>{panchayat?.district ?? block?.district ?? dash}</span><i>›</i><span>{panchayat?.block_name ?? block?.block_name ?? dash}</span>
          </div>
          <button type="button" className="cc-icon-btn cc-icon-btn-sm" onClick={onClose} aria-label="Close Panchayat details"><IconClose width={18} height={18} /></button>
        </div>

        <h2 className="cc-sheet-title">{name}</h2>

        {loading ? (
          <SheetSkeleton />
        ) : error ? (
          <div className="cc-error" role="alert">
            <IconAlert width={18} height={18} />
            <div><strong>Couldn't load this forecast</strong><p>{error}</p></div>
            <button type="button" className="cc-btn-sm" onClick={onRetry}><IconRefresh width={15} height={15} /> Retry</button>
          </div>
        ) : !forecast || !today ? (
          <div className="cc-card-muted"><Unavailable>No forecast is available for this Panchayat yet.</Unavailable></div>
        ) : (
          <>
            <div className="cc-hero">
              <div className="cc-temp" aria-label={`High ${n0(today.tmax)} degrees`}>{n0(today.tmax)}<span>°</span></div>
              <div className="cc-hero-meta">
                <span className="cc-hero-day">{lab.isToday ? "Today" : lab.long} · forecast high</span>
                <span className="cc-hero-low">Low {n0(today.tmin)}°</span>
              </div>
              {isNum(userDistanceKm) && <span className="cc-away">{formatKm(userDistanceKm)} from you</span>}
            </div>

            <div className="cc-stats">
              <Stat icon={<IconRain width={17} height={17} />} label="Rain" value={n1(today.rain)} unit=" mm" />
              <Stat icon={<IconDrops width={17} height={17} />} label="Humidity" value={n0(today.humidity)} unit="%" />
              <Stat icon={<IconWind width={17} height={17} />} label="Wind" value={n0(today.wind)} unit=" km/h" />
            </div>

            <div className="cc-chips">
              {isMocked
                ? <Chip tone="warn" icon={<IconAlert width={14} height={14} />} title="The live weather service was unreachable; this is a fixed offline sample, not a forecast.">Sample data (offline)</Chip>
                : <Chip tone="ok" title={`Block forecast from ${forecast.block_source?.source}`}>Live · {forecast.block_source?.source}</Chip>}
              <Chip tone="neutral" title="Panchayat values are derived from the block forecast with a transparent baseline method, not a trained model.">
                {forecast.method === "baseline" ? "Baseline estimate" : "ML-corrected"}
              </Chip>
              {panchayat?.is_demo_data && <Chip tone="neutral" title="Placeholder Panchayat with approximate coordinates; not an official administrative unit.">Demo location</Chip>}
              {insights.anyAvailable
                ? [["Weather", insights.weatherRisk], ["Crop", insights.cropRisk], ["Disease", insights.diseaseRisk]]
                    .filter(([, s]) => s.available)
                    .map(([l, s]) => <Chip key={l} tone="risk">{l} risk: {s.label ?? s.level}</Chip>)
                : <Chip tone="off" icon={<IconInfo width={14} height={14} />} title="Crop and disease risk are not available from the current data source.">Crop &amp; disease risk: not in current data</Chip>}
            </div>

            {facts.length > 0 && (
              <ul className="cc-facts" aria-label="Forecast highlights">
                {facts.map((f) => <li key={f.id}>{HIGHLIGHT_ICON[f.kind]}{f.text}</li>)}
              </ul>
            )}

            {insights.advisory.available && (
              <div className="cc-advisory cc-advisory-peek">
                <span className="cc-eyebrow">Recommended action</span>
                <p>{insights.advisory.title ?? insights.advisory.text}</p>
              </div>
            )}

            {isSheet && (
              <button type="button" className="cc-expand" onClick={onToggleExpanded} aria-expanded={expanded} aria-controls="cc-sheet-more">
                {expanded ? <>Hide details <IconChevronDown width={16} height={16} /></> : <>Forecast &amp; graphs <IconChevronUp width={16} height={16} /></>}
              </button>
            )}
          </>
        )}
      </div>

      {!loading && !error && forecast && today && (
        <div id="cc-sheet-more" className="cc-sheet-more" aria-hidden={isSheet && !expanded}>
          <div className="cc-sheet-pad">
            <section className="cc-section" aria-labelledby="cc-fc-h">
              <h3 id="cc-fc-h" className="cc-section-h">Next {daily.length} days <small>Forecast</small></h3>
              <div className="cc-charts">
                <TemperatureChart daily={daily} now={now} />
                <RainfallChart daily={daily} now={now} />
                <HumidityChart daily={daily} now={now} />
                <WindChart daily={daily} now={now} />
              </div>
            </section>

            <RiskAndAdvisory insights={insights} onOpenCropHealth={onOpenCropHealth} />
            <Compare forecast={forecast} />
            <Method forecast={forecast} />

            <section className="cc-section" aria-labelledby="cc-loc-h">
              <h3 id="cc-loc-h" className="cc-section-h">Location</h3>
              <dl className="cc-kv">
                <div><dt>Coordinates</dt><dd>{panchayat ? `${panchayat.latitude.toFixed(3)}, ${panchayat.longitude.toFixed(3)}` : dash}</dd></div>
                <div><dt>Elevation</dt><dd>{isNum(panchayat?.elevation_m) ? `${Math.round(panchayat.elevation_m)} m` : dash}</dd></div>
                <div><dt>Block</dt><dd>{panchayat?.block_name ?? dash}</dd></div>
                <div><dt>Region</dt><dd>{panchayat?.state ?? dash}</dd></div>
              </dl>
            </section>

            <div className="cc-links">
              <button type="button" className="cc-link-btn" onClick={() => onNavigate("weather", panchayat?.panchayat_id)}><IconTable width={16} height={16} /> Day-by-day table</button>
              <button type="button" className="cc-link-btn" onClick={() => onNavigate("dashboard")}><IconCompare width={16} height={16} /> Compare all Panchayats</button>
            </div>
            <p className="cc-foot">Forecast values are daily: temperature high/low, rainfall total, mean humidity and maximum wind. Map © OpenStreetMap contributors.</p>
          </div>
        </div>
      )}

      {/* Charts are not mounted until the forecast is ready; show matching skeletons while a retry loads. */}
      {loading && <div className="cc-sheet-more"><div className="cc-sheet-pad"><ChartSkeletons /></div></div>}
    </section>
  );
}
