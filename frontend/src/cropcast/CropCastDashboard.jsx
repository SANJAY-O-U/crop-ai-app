import { useState } from "react";
import { useBlockData } from "./useBlockData";
import { DemoDataBanner, ErrorCard, LoadingCard, MethodBadge, SourceBadge, VARIABLES } from "./shared";

function ComparisonBars({ block, forecasts, variableKey, unit, color }) {
  const rows = [
    { label: "Block (source)", value: block.daily[0][variableKey], isBlock: true },
    ...forecasts.map((f) => ({ label: f.panchayat_name, value: f.daily[0][variableKey], isBlock: false })),
  ];
  const max = Math.max(...rows.map((r) => r.value), 1);

  return (
    <div>
      {rows.map((row) => (
        <div key={row.label} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
            <span style={{ fontWeight: row.isBlock ? 700 : 500, color: row.isBlock ? "var(--text)" : "var(--text2)" }}>
              {row.label}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontWeight: 700, color }}>
              {row.value.toFixed(1)} {unit}
            </span>
          </div>
          <div style={{ height: 8, background: "var(--border-bg)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 4, width: `${(row.value / max) * 100}%`,
              background: row.isBlock ? "var(--text3)" : color,
              opacity: row.isBlock ? 0.6 : 1,
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function CropCastDashboard({ onNavigate }) {
  const { loading, error, block, forecasts } = useBlockData(3);
  const [variable, setVariable] = useState(VARIABLES[0]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "48px 5%" }}>
      <button onClick={() => onNavigate("home")} style={{ background: "none", border: "1px solid var(--border)", color: "var(--text2)", padding: "6px 14px", borderRadius: 8, cursor: "pointer", fontSize: 13, marginBottom: 18 }}>
        ← Map
      </button>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase", color: "var(--green)", marginBottom: 10 }}>
        CropCastAI · Weather Intelligence · SIH26074
      </div>
      <h1 style={{ fontFamily: "var(--display)", fontSize: "clamp(1.8rem,4vw,2.4rem)", fontWeight: 800, letterSpacing: "-1px", marginBottom: 10 }}>
        Block → Panchayat Weather Dashboard
      </h1>
      <p style={{ color: "var(--text2)", marginBottom: 24, maxWidth: 640 }}>
        One coarse block-level forecast, downscaled into three localized panchayat estimates.
        This is Phase 1: the foundation pipeline, not the finished advisory product.
      </p>

      <DemoDataBanner />

      {loading && <LoadingCard label="Loading pilot block data…" />}
      {error && <ErrorCard message={error} />}

      {!loading && !error && block && (
        <>
          {/* Block summary strip */}
          <div className="card" style={{ padding: 22, marginBottom: 24, display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text3)", letterSpacing: 1, marginBottom: 4 }}>PILOT BLOCK</div>
              <div style={{ fontFamily: "var(--display)", fontWeight: 800, fontSize: "1.2rem" }}>{block.block_name}</div>
              <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>
                {block.district}, {block.state} · elevation {block.elevation_m ?? "—"} m · {block.latitude.toFixed(3)}, {block.longitude.toFixed(3)}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <MethodBadge method={forecasts[0]?.method} />
            </div>
          </div>

          {/* THE core comparison: block vs every panchayat, one variable at a time */}
          <div className="card" style={{ padding: 24, marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18, flexWrap: "wrap", gap: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text2)", letterSpacing: 0.5 }}>
                TODAY — BLOCK FORECAST vs PANCHAYAT ESTIMATE
              </div>
              <div style={{ display: "flex", gap: 6 }}>
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
            </div>

            {forecasts[0] && (
              <ComparisonBars
                block={forecasts[0].block_source}
                forecasts={forecasts}
                variableKey={variable.key}
                unit={variable.unit}
                color={variable.color}
              />
            )}
            <div style={{ marginTop: 4 }}>
              <SourceBadge source={forecasts[0]?.block_source.source} isMocked={forecasts[0]?.block_source.is_mocked} />
            </div>
          </div>

          {/* Quick nav into the two other screens */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={() => onNavigate("weather")}>
              📊 Panchayat Weather detail →
            </button>
            <button className="btn btn-ghost" onClick={() => onNavigate("map")}>
              🗺️ Open Weather Map →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
