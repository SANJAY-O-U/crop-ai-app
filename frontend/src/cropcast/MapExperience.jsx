import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./cropcast.css";
import "./polish.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useBlockData } from "./useBlockData";
import { useGeolocation, useMediaQuery } from "./hooks";
import PanchayatSheet from "./PanchayatSheet";
import { VARIABLES } from "./shared";
import { LAYER_SCALES, extent, formatKm, inkFor, isNum, layerColor, nearestPanchayat } from "./forecastModel";
import { IconAlert, IconClose, IconInfo, IconLayers, IconLocate, IconLock, IconMinus, IconPin, IconPlus, IconRefresh } from "./icons";

const OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const FORECAST_DAYS = 7;
const PANEL_QUERY = "(min-width: 1024px)";
const PANEL_WIDTH = 424;

const LAYER_SUB = {
  rainfall_mm: "Daily total",
  temperature_max_c: "Daily high",
  humidity_pct: "Daily mean",
  wind_kmph: "Daily maximum",
};

function pinText(key, v) {
  if (!isNum(v)) return "—";
  if (key === "temperature_max_c") return `${Math.round(v)}°`;
  if (key === "rainfall_mm") return `${v < 10 ? v.toFixed(1) : Math.round(v)} mm`;
  if (key === "humidity_pct") return `${Math.round(v)}%`;
  return `${Math.round(v)} km/h`;
}

function pinIcon({ text, bg, ink, selected, missing }) {
  // `text`, `bg` and `ink` are generated from numbers/colours only — never from API strings.
  return L.divIcon({
    className: "cc-pin-wrap",
    html: `<div class="cc-pin${selected ? " is-selected" : ""}${missing ? " is-missing" : ""}" style="--pin-bg:${bg};--pin-ink:${ink}"><span>${text}</span></div>`,
    iconSize: [80, 54],
    iconAnchor: [40, 52],
  });
}

const blockIcon = () =>
  L.divIcon({ className: "cc-pin-wrap", html: '<div class="cc-block-dot"><span>Block</span></div>', iconSize: [56, 28], iconAnchor: [28, 14] });

const userIcon = () =>
  L.divIcon({ className: "cc-pin-wrap", html: '<div class="cc-user"><i></i><b></b></div>', iconSize: [28, 28], iconAnchor: [14, 14] });

function LayersPanel({ variable, onPick, onClose }) {
  return (
    <div className="cc-layers" role="dialog" aria-label="Map layers">
      <div className="cc-layers-head">
        <h3>Map layers</h3>
        <button type="button" className="cc-icon-btn cc-icon-btn-sm" onClick={onClose} aria-label="Close layers"><IconClose width={18} height={18} /></button>
      </div>
      <p className="cc-layers-sub"><span className="cc-dot-on" />Available · weather forecast</p>
      <div role="radiogroup" aria-label="Weather layer" className="cc-layer-list">
        {VARIABLES.map((v) => {
          const active = v.key === variable.key;
          const [lo, hi] = LAYER_SCALES[v.key];
          return (
            <button key={v.key} type="button" role="radio" aria-checked={active} className={`cc-layer ${active ? "is-active" : ""}`} onClick={() => onPick(v)}>
              <span className="cc-layer-sw" style={{ background: `linear-gradient(90deg, ${lo}, ${hi})` }} aria-hidden="true" />
              <span className="cc-layer-txt"><strong>{v.label}</strong><small>{LAYER_SUB[v.key]} · {v.unit}</small></span>
              <span className="cc-radio" aria-hidden="true" />
            </button>
          );
        })}
      </div>
      <p className="cc-layers-sub cc-layers-sub-off"><span className="cc-dot-off" />Not available yet</p>
      <div className="cc-layer-list">
        {["Crop risk", "Disease risk"].map((name) => (
          <div key={name} className="cc-layer is-disabled" aria-disabled="true">
            <span className="cc-layer-sw cc-layer-sw-off" aria-hidden="true"><IconLock /></span>
            <span className="cc-layer-txt"><strong>{name}</strong><small>Not available from current data source</small></span>
          </div>
        ))}
      </div>
      <p className="cc-layers-foot">Base map © OpenStreetMap contributors</p>
    </div>
  );
}

export default function MapExperience({ onNavigate, onOpenCropHealth }) {
  const { loading, error, block, panchayats, forecasts, reload } = useBlockData(FORECAST_DAYS);
  const geo = useGeolocation();
  const isPanel = useMediaQuery(PANEL_QUERY);

  const [variable, setVariable] = useState(VARIABLES[1]); // daily high temperature: the most immediately readable layer
  const [selectedId, setSelectedId] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [tileProblem, setTileProblem] = useState(false);

  const wrapRef = useRef(null);
  const mapDivRef = useRef(null);
  const mapRef = useRef(null);
  const pinsRef = useRef(null);
  const userLayerRef = useRef(null);
  const sheetRef = useRef(null);
  const summaryRef = useRef(null);
  const didFitRef = useRef(false);
  const handlersRef = useRef({});

  const forecastById = useMemo(() => new Map(forecasts.map((f) => [f.panchayat_id, f])), [forecasts]);
  const selected = panchayats.find((p) => p.panchayat_id === selectedId) ?? null;
  const selectedForecast = selected ? forecastById.get(selected.panchayat_id) : undefined;

  // Layer value per Panchayat (first forecast day) and the colour domain.
  const valueOf = useCallback((id) => forecastById.get(id)?.daily?.[0]?.[variable.key], [forecastById, variable]);
  const blockValue = forecasts[0]?.block_source?.daily?.[0]?.[variable.key];
  const domain = useMemo(() => {
    const vals = [...panchayats.map((p) => valueOf(p.panchayat_id)), blockValue].filter(isNum);
    return vals.length ? { min: Math.min(...vals), max: Math.max(...vals) } : null;
  }, [panchayats, valueOf, blockValue]);
  const scale = LAYER_SCALES[variable.key];
  const colorOf = useCallback((v) => layerColor(v, domain?.min, domain?.max, scale), [domain, scale]);

  const select = useCallback((id) => { setSelectedId(id); setExpanded(false); setLayersOpen(false); }, []);
  const closeSheet = useCallback(() => { setSelectedId(null); setExpanded(false); }, []);
  const showToast = useCallback((t) => setToast({ id: Date.now(), ...t }), []);

  handlersRef.current = { select, closeSheet, expanded };

  // ── Map init (once) ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return undefined;
    const map = L.map(mapDivRef.current, { zoomControl: false, minZoom: 4, maxZoom: 17, zoomSnap: 0.5, worldCopyJump: false }).setView([13.4, 77.73], 10);
    map.attributionControl.setPrefix(false);
    const tiles = L.tileLayer(OSM_URL, { attribution: "© OpenStreetMap contributors", maxZoom: 19 }).addTo(map);
    let errs = 0;
    tiles.on("tileerror", () => { errs += 1; if (errs >= 4) setTileProblem(true); });
    tiles.on("tileload", () => { if (errs) { errs = 0; setTileProblem(false); } });
    map.on("click", () => { if (!handlersRef.current.expanded) handlersRef.current.closeSheet(); });
    pinsRef.current = L.layerGroup().addTo(map);
    userLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; pinsRef.current = null; userLayerRef.current = null; didFitRef.current = false; };
  }, []);

  // ── Pins: redrawn whenever data, layer or selection changes ────────────────
  useEffect(() => {
    const layer = pinsRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (block && isNum(block.latitude) && isNum(block.longitude)) {
      L.marker([block.latitude, block.longitude], { icon: blockIcon(), keyboard: false, zIndexOffset: -200 })
        .bindTooltip(`${block.block_name} — block centroid (the coarse forecast point)${isNum(blockValue) ? ` · ${pinText(variable.key, blockValue)}` : ""}`, { direction: "top", offset: [0, -8] })
        .addTo(layer);
    }
    panchayats.forEach((p) => {
      if (!isNum(p.latitude) || !isNum(p.longitude)) return;
      const v = valueOf(p.panchayat_id);
      const bg = colorOf(v);
      const marker = L.marker([p.latitude, p.longitude], {
        icon: pinIcon({ text: pinText(variable.key, v), bg, ink: isNum(v) ? inkFor(bg) : "#44564a", selected: p.panchayat_id === selectedId, missing: !isNum(v) }),
        title: p.panchayat_name, keyboard: true, riseOnHover: true, zIndexOffset: p.panchayat_id === selectedId ? 1000 : 0,
      });
      marker.on("click", (e) => { L.DomEvent.stopPropagation(e); handlersRef.current.select(p.panchayat_id); });
      marker.addTo(layer);
      marker.getElement()?.setAttribute("aria-label", `${p.panchayat_name}: ${variable.label} ${pinText(variable.key, v)}. Open details.`);
    });
  }, [block, panchayats, valueOf, colorOf, variable, selectedId, blockValue]);

  // ── Fit the pilot area once the data arrives ───────────────────────────────
  const fitPilot = useCallback((animate = true) => {
    const map = mapRef.current;
    if (!map || !block || !panchayats.length) return;
    const pts = [[block.latitude, block.longitude], ...panchayats.filter((p) => isNum(p.latitude) && isNum(p.longitude)).map((p) => [p.latitude, p.longitude])];
    map.fitBounds(L.latLngBounds(pts), { paddingTopLeft: [isPanel ? PANEL_WIDTH + 40 : 40, 110], paddingBottomRight: [64, isPanel ? 56 : 170], maxZoom: 12, animate });
  }, [block, panchayats, isPanel]);

  useEffect(() => {
    if (didFitRef.current || !block || !panchayats.length) return;
    fitPilot(false);
    didFitRef.current = true;
  }, [block, panchayats, fitPilot]);

  // ── Centre the selected Panchayat in the part of the map not covered by the sheet/panel ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selected || !isNum(selected.latitude)) return undefined;
    const raf = requestAnimationFrame(() => {
      const zoom = Math.max(map.getZoom(), 11);
      const pt = map.project(L.latLng(selected.latitude, selected.longitude), zoom);
      const sheetH = isPanel ? 0 : sheetRef.current?.offsetHeight ?? 300;
      const center = map.unproject(pt.subtract([isPanel ? PANEL_WIDTH / 2 : 0, 0]).add([0, sheetH / 2]), zoom);
      map.flyTo(center, zoom, { duration: 0.6 });
    });
    return () => cancelAnimationFrame(raf);
  }, [selectedId, isPanel]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Expose the sheet height to CSS so floating controls sit above it ───────
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return undefined;
    const sheet = sheetRef.current;
    const summary = summaryRef.current;
    if (!sheet || !selected) { wrap.style.setProperty("--sheet-h", "0px"); return undefined; }
    const update = () => {
      wrap.style.setProperty("--sheet-h", isPanel ? "0px" : `${sheet.offsetHeight}px`);
      wrap.style.setProperty("--summary-h", `${summary?.offsetHeight ?? 240}px`);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(sheet);
    if (summary) ro.observe(summary);
    return () => ro.disconnect();
  }, [selectedId, isPanel, expanded, loading, selectedForecast]);

  // Keep the active chip visible in the scrolling row.
  useEffect(() => {
    if (!selectedId) return;
    const row = wrapRef.current?.querySelector(".cc-chiprow");
    const chip = row?.querySelector(".cc-pchip.is-active");
    if (!row || !chip) return;
    const target = chip.offsetLeft - (row.clientWidth - chip.offsetWidth) / 2;
    row.scrollLeft = Math.max(0, target);
  }, [selectedId]);

  // ── Keyboard: Esc closes the layers panel, then the sheet ──────────────────
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      if (layersOpen) setLayersOpen(false);
      else if (selectedId) closeSheet();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [layersOpen, selectedId, closeSheet]);

  // ── Current location ───────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    const layer = userLayerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    if (geo.status !== "ready" || !geo.position) return;
    const { lat, lon, accuracy } = geo.position;
    if (isNum(accuracy) && accuracy < 8000) L.circle([lat, lon], { radius: accuracy, className: "cc-accuracy", interactive: false }).addTo(layer);
    L.marker([lat, lon], { icon: userIcon(), keyboard: false, interactive: false, zIndexOffset: 2000 }).addTo(layer);
  }, [geo.status, geo.position]);

  useEffect(() => {
    if (geo.status === "ready" && geo.position) {
      mapRef.current?.flyTo([geo.position.lat, geo.position.lon], 12.5, { duration: 0.8 });
      const near = nearestPanchayat(geo.position.lat, geo.position.lon, panchayats);
      if (!near) showToast({ tone: "info", text: "You are here. No Panchayat data has loaded yet." });
      else if (near.km <= 30) showToast({ tone: "info", text: `Nearest Panchayat: ${near.panchayat.panchayat_name} · ${formatKm(near.km)} away`, actionLabel: "Open", onAction: () => select(near.panchayat.panchayat_id) });
      else showToast({ tone: "info", text: `The nearest pilot Panchayat is ${formatKm(near.km)} away. This demo covers only one small area.`, actionLabel: "Show pilot area", onAction: () => fitPilot(true) });
    } else if (["denied", "timeout", "unavailable", "unsupported"].includes(geo.status)) {
      showToast({ tone: "error", text: geo.message });
    }
  }, [geo.status, geo.position]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(t);
  }, [toast]);

  const range = domain ? `${pinText(variable.key, domain.min)} – ${pinText(variable.key, domain.max)}` : null;
  const userNear = geo.status === "ready" && geo.position && selected ? nearestPanchayat(geo.position.lat, geo.position.lon, [selected]) : null;
  const showHint = !selected && !loading && !error && panchayats.length > 0;

  return (
    <div ref={wrapRef} className={`cc-map-wrap ${isPanel ? "is-desktop" : "is-mobile"} ${selected ? "has-sheet" : ""} ${expanded ? "sheet-expanded" : ""}`}>
      <div ref={mapDivRef} className="cc-map" role="application" aria-label="Map of Panchayats. Select a Panchayat marker to see its weather." />

      {/* Top: Panchayat chips + legend */}
      <div className="cc-top">
        <div className="cc-chiprow" role="group" aria-label="Panchayats">
          {loading && !panchayats.length && [0, 1, 2].map((i) => <span key={i} className="cc-skel cc-pchip-skel" />)}
          {panchayats.map((p) => {
            const v = valueOf(p.panchayat_id);
            return (
              <button key={p.panchayat_id} type="button" className={`cc-pchip ${p.panchayat_id === selectedId ? "is-active" : ""}`} aria-pressed={p.panchayat_id === selectedId} onClick={() => select(p.panchayat_id)}>
                <span className="cc-pchip-dot" style={{ background: colorOf(v) }} aria-hidden="true" />
                {p.panchayat_name}<em>{pinText(variable.key, v)}</em>
              </button>
            );
          })}
        </div>
        {domain && (
          <div className="cc-legend" aria-label={`${variable.label} legend`}>
            <span className="cc-legend-bar" style={{ background: `linear-gradient(90deg, ${scale[0]}, ${scale[1]})` }} aria-hidden="true" />
            <span><strong>{variable.label}</strong> · {LAYER_SUB[variable.key].toLowerCase()} · {range}</span>
          </div>
        )}
      </div>

      {/* Right: floating controls */}
      <div className="cc-controls" role="group" aria-label="Map controls">
        <button type="button" className={`cc-fab ${geo.status === "ready" ? "is-on" : ""}`} onClick={geo.locate} disabled={geo.status === "locating"} aria-label="Show my location" title="My location">
          {geo.status === "locating" ? <span className="cc-spinner cc-spinner-sm" /> : <IconLocate />}
        </button>
        <button type="button" className={`cc-fab ${layersOpen ? "is-on" : ""}`} onClick={() => setLayersOpen((o) => !o)} aria-label="Map layers" aria-expanded={layersOpen} title="Map layers"><IconLayers /></button>
        <button type="button" className="cc-fab" onClick={() => fitPilot(true)} aria-label="Show all Panchayats" title="Show all Panchayats" disabled={!panchayats.length}><IconPin /></button>
        <div className="cc-zoom">
          <button type="button" className="cc-fab" onClick={() => mapRef.current?.zoomIn()} aria-label="Zoom in"><IconPlus /></button>
          <button type="button" className="cc-fab" onClick={() => mapRef.current?.zoomOut()} aria-label="Zoom out"><IconMinus /></button>
        </div>
      </div>

      {layersOpen && (
        <>
          <button type="button" className="cc-scrim" aria-label="Close layers" onClick={() => setLayersOpen(false)} />
          <LayersPanel variable={variable} onPick={(v) => setVariable(v)} onClose={() => setLayersOpen(false)} />
        </>
      )}

      {selected && (
        <PanchayatSheet
          mode={isPanel ? "panel" : "sheet"}
          expanded={expanded}
          onToggleExpanded={() => setExpanded((e) => !e)}
          onClose={closeSheet}
          panchayat={selected}
          forecast={selectedForecast}
          block={block}
          loading={loading}
          error={error && !loading ? error : null}
          onRetry={reload}
          onNavigate={onNavigate}
          onOpenCropHealth={onOpenCropHealth}
          sheetRef={sheetRef}
          summaryRef={summaryRef}
          userDistanceKm={userNear?.km}
        />
      )}

      {showHint && <div className="cc-hint" role="status"><IconPin width={16} height={16} /> Tap a Panchayat on the map</div>}

      {loading && !forecasts.length && !error && (
        <div className="cc-status" role="status"><span className="cc-spinner" /> Loading Panchayats and forecasts…</div>
      )}

      {error && !panchayats.length && (
        <div className="cc-status cc-status-error" role="alert">
          <IconAlert width={22} height={22} />
          <div><strong>Can't load Panchayat data</strong><p>{error}</p></div>
          <button type="button" className="cc-btn-sm" onClick={reload}><IconRefresh width={15} height={15} /> Try again</button>
        </div>
      )}

      {tileProblem && (
        <div className="cc-tileissue" role="status"><IconInfo width={16} height={16} /> Map tiles aren't loading. Check your connection; weather data is unaffected.</div>
      )}

      {toast && (
        <div className={`cc-toast cc-toast-${toast.tone}`} role="status" aria-live="polite">
          <span>{toast.text}</span>
          {toast.actionLabel && <button type="button" onClick={() => { toast.onAction?.(); setToast(null); }}>{toast.actionLabel}</button>}
          <button type="button" className="cc-toast-x" onClick={() => setToast(null)} aria-label="Dismiss"><IconClose width={16} height={16} /></button>
        </div>
      )}
    </div>
  );
}
