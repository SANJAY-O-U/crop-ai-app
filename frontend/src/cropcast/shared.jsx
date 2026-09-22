// Small shared bits used by all three CropCast Phase 1 screens.

export function DemoDataBanner() {
  return (
    <div style={{
      padding: "10px 16px", borderRadius: 10, marginBottom: 20, fontSize: 12, lineHeight: 1.6,
      background: "rgba(202,138,4,0.08)", border: "1px solid rgba(202,138,4,0.3)", color: "#92650a",
    }}>
      <strong>Demo data — Phase 1 pilot:</strong> one block and 3 panchayats with placeholder IDs and
      approximate (not official-survey) coordinates. Weather is downscaled with a transparent{" "}
      <em>baseline</em> method, not a trained ML model yet.
    </div>
  );
}

export function LoadingCard({ label = "Loading…" }) {
  return (
    <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--text3)", fontSize: 13 }}>
      {label}
    </div>
  );
}

export function ErrorCard({ message }) {
  return (
    <div style={{
      padding: "14px 16px", borderRadius: 10, fontSize: 13,
      background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.25)", color: "#dc2626",
    }}>
      ⚠️ {message}
    </div>
  );
}

export function MethodBadge({ method }) {
  const isBaseline = method === "baseline";
  return (
    <span style={{
      fontSize: 10, fontWeight: 800, letterSpacing: 0.4, padding: "3px 9px", borderRadius: 20,
      background: isBaseline ? "rgba(202,138,4,0.12)" : "rgba(76,175,80,0.12)",
      color: isBaseline ? "#92650a" : "var(--green)",
    }}>
      {isBaseline ? "BASELINE — not ML" : "ML-CORRECTED"}
    </span>
  );
}

export function SourceBadge({ source, isMocked }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 20,
      background: isMocked ? "rgba(220,38,38,0.1)" : "rgba(2,132,199,0.1)",
      color: isMocked ? "#dc2626" : "#0284c7",
    }}>
      {isMocked ? "MOCK (offline fallback)" : `live: ${source}`}
    </span>
  );
}

export const VARIABLES = [
  { key: "rainfall_mm",       label: "Rainfall",    unit: "mm",  color: "#0284c7" },
  { key: "temperature_max_c", label: "Max Temp",    unit: "°C",  color: "#ea580c" },
  { key: "humidity_pct",      label: "Humidity",    unit: "%",   color: "#16a34a" },
  { key: "wind_kmph",         label: "Wind",        unit: "km/h", color: "#7c3aed" },
];
