import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import { useBlockData } from "./useBlockData";
import { DemoDataBanner, ErrorCard, LoadingCard, VARIABLES } from "./shared";

function lerpColor(t, low, high) {
  const l = low.match(/\w\w/g).map((h) => parseInt(h, 16));
  const h = high.match(/\w\w/g).map((h2) => parseInt(h2, 16));
  const rgb = l.map((c, i) => Math.round(c + (h[i] - c) * t));
  return `rgb(${rgb.join(",")})`;
}

// Low/high hex colors per variable — kept simple, no charting library.
const SCALES = {
  rainfall_mm:       ["#dff2ff", "#0284c7"],
  temperature_max_c: ["#fef3c7", "#dc2626"],
  humidity_pct:      ["#f0fdf4", "#16a34a"],
  wind_kmph:         ["#f5f3ff", "#7c3aed"],
};

export default function WeatherMapPage({ onNavigate }) {
  const { loading, error, block, panchayats, forecasts } = useBlockData(1);
  const [variable, setVariable] = useState(VARIABLES[0]);

  const mapDivRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  // Init map once
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;
    const map = L.map(mapDivRef.current, { zoomControl: true }).setView([13.4, 77.73], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 15,
    }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // (Re)draw markers whenever data or the selected variable changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || loading || error || !block || forecasts.length === 0 || panchayats.length === 0) return;

    if (layerRef.current) layerRef.current.remove();
    const layer = L.layerGroup().addTo(map);
    layerRef.current = layer;

    const blockVal = forecasts[0].block_source.daily[0][variable.key];
    const values = [blockVal, ...forecasts.map((f) => f.daily[0][variable.key])];
    const min = Math.min(...values);
    const max = Math.max(...values);
    const [low, high] = SCALES[variable.key];
    const colorFor = (v) => (max === min ? high : lerpColor((v - min) / (max - min), low, high));

    // Block marker — larger, neutral-ringed square-ish circle
    L.circleMarker([block.latitude, block.longitude], {
      radius: 14, color: "#111811", weight: 2, fillColor: colorFor(blockVal), fillOpacity: 0.9,
    })
      .bindPopup(`<strong>${block.block_name}</strong> (block)<br/>${variable.label}: ${blockVal.toFixed(1)} ${variable.unit}`)
      .addTo(layer);

    forecasts.forEach((f) => {
      const panchayat = panchayats.find((p) => p.panchayat_id === f.panchayat_id);
      if (!panchayat) return; // shouldn't happen, but don't plot a point with no known location
      const val = f.daily[0][variable.key];
      L.circleMarker([panchayat.latitude, panchayat.longitude], {
        radius: 10, color: "#2d7a31", weight: 1.5, fillColor: colorFor(val), fillOpacity: 0.9,
      })
        .bindPopup(`<strong>${f.panchayat_name}</strong><br/>${variable.label}: ${val.toFixed(1)} ${variable.unit}<br/>Elevation Δ: ${f.adjustment.elevation_delta_m ?? "—"} m`)
        .addTo(layer);
    });

    const bounds = L.latLngBounds([
      [block.latitude, block.longitude],
      ...panchayats.map((p) => [p.latitude, p.longitude]),
    ]);
    map.fitBounds(bounds.pad(0.3));
  }, [loading, error, block, panchayats, forecasts, variable]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "48px 5%" }}>
      <button onClick={() => onNavigate("home")} style={{ background: "none", border: "1px solid var(--border)", color: "var(--text2)", padding: "6px 14px", borderRadius: 8, cursor: "pointer", fontSize: 13, marginBottom: 18 }}>
        ← Map
      </button>
      <h1 style={{ fontFamily: "var(--display)", fontSize: "clamp(1.6rem,4vw,2.2rem)", fontWeight: 800, marginBottom: 8 }}>
        Weather Map
      </h1>
      <p style={{ color: "var(--text2)", marginBottom: 20 }}>
        The block centroid (dark ring) vs. its panchayats (green ring), colored by the selected variable.
      </p>

      <DemoDataBanner />

      {loading && <LoadingCard label="Loading map data…" />}
      {error && <ErrorCard message={error} />}

      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {VARIABLES.map((v) => (
          <button key={v.key} onClick={() => setVariable(v)}
            style={{
              padding: "6px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
              border: `1.5px solid ${variable.key === v.key ? v.color : "var(--border)"}`,
              background: variable.key === v.key ? `${v.color}18` : "transparent",
              color: variable.key === v.key ? v.color : "var(--text2)", fontWeight: 600,
            }}>
            {v.label}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 12 }}>
        <div ref={mapDivRef} style={{ height: 440, width: "100%" }} />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--text3)" }}>
        <span>Low {variable.label}</span>
        <div style={{ width: 120, height: 10, borderRadius: 6, background: `linear-gradient(90deg, ${SCALES[variable.key][0]}, ${SCALES[variable.key][1]})` }} />
        <span>High {variable.label}</span>
      </div>
    </div>
  );
}
