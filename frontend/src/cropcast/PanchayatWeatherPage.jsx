import { useState } from "react";
import { useBlockData } from "./useBlockData";
import { DemoDataBanner, ErrorCard, LoadingCard, MethodBadge, SourceBadge, VARIABLES } from "./shared";

function ComparisonTable({ forecast, variable }) {
  const blockDaily = forecast.block_source.daily;
  const panchDaily = forecast.daily;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ textAlign: "left", color: "var(--text3)", fontSize: 11, letterSpacing: 0.5 }}>
          <th style={{ padding: "6px 8px" }}>DATE</th>
          <th style={{ padding: "6px 8px" }}>BLOCK</th>
          <th style={{ padding: "6px 8px" }}>{forecast.panchayat_name.toUpperCase()}</th>
          <th style={{ padding: "6px 8px" }}>DELTA</th>
        </tr>
      </thead>
      <tbody>
        {blockDaily.map((bDay, i) => {
          const pDay = panchDaily[i];
          const bVal = bDay[variable.key];
          const pVal = pDay[variable.key];
          const delta = pVal - bVal;
          return (
            <tr key={bDay.date} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "8px" }}>{bDay.date}</td>
              <td style={{ padding: "8px", fontFamily: "var(--mono)" }}>{bVal.toFixed(1)} {variable.unit}</td>
              <td style={{ padding: "8px", fontFamily: "var(--mono)", fontWeight: 700, color: variable.color }}>
                {pVal.toFixed(1)} {variable.unit}
              </td>
              <td style={{ padding: "8px", fontFamily: "var(--mono)", color: delta === 0 ? "var(--text3)" : delta > 0 ? "#dc2626" : "#0284c7" }}>
                {delta > 0 ? "+" : ""}{delta.toFixed(1)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AdjustmentCard({ adjustment }) {
  if (adjustment.elevation_delta_m === null) {
    return <ErrorCard message={adjustment.note} />;
  }
  return (
    <div style={{ padding: "14px 16px", borderRadius: 10, background: "var(--bg2)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text2)", lineHeight: 1.8 }}>
      <div style={{ fontWeight: 700, marginBottom: 6, color: "var(--text)" }}>How this estimate was derived</div>
      Elevation delta vs. block: <strong>{adjustment.elevation_delta_m > 0 ? "+" : ""}{adjustment.elevation_delta_m} m</strong>
      {" "}({adjustment.panchayat_elevation_m} m panchayat − {adjustment.block_elevation_m} m block)
      <br />
      Temperature uses the standard atmospheric lapse rate ({adjustment.temperature_lapse_rate_c_per_m} °C/m — real physics).
      <br />
      Rainfall/humidity/wind use placeholder heuristic coefficients (
        rainfall {adjustment.rainfall_orographic_factor_per_100m >= 0 ? "+" : ""}{(adjustment.rainfall_orographic_factor_per_100m * 100).toFixed(0)}%/100m,{" "}
        humidity {adjustment.humidity_adjustment_pct_per_100m}pp/100m,{" "}
        wind {adjustment.wind_factor_per_100m >= 0 ? "+" : ""}{(adjustment.wind_factor_per_100m * 100).toFixed(0)}%/100m
      ) — <strong>not calibrated</strong> against real observations yet (Phase 2 work).
    </div>
  );
}

export default function PanchayatWeatherPage({ onNavigate, initialPanchayatId = null }) {
  const { loading, error, panchayats, forecasts } = useBlockData(5);
  const [selectedId, setSelectedId] = useState(initialPanchayatId);
  const [variable, setVariable] = useState(VARIABLES[0]);

  const forecast = forecasts.find((f) => f.panchayat_id === (selectedId ?? forecasts[0]?.panchayat_id));

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "48px 5%" }}>
      <button onClick={() => onNavigate("home")} style={{ background: "none", border: "1px solid var(--border)", color: "var(--text2)", padding: "6px 14px", borderRadius: 8, cursor: "pointer", fontSize: 13, marginBottom: 18 }}>
        ← Map
      </button>
      <h1 style={{ fontFamily: "var(--display)", fontSize: "clamp(1.6rem,4vw,2.2rem)", fontWeight: 800, marginBottom: 8 }}>
        Panchayat Weather
      </h1>
      <p style={{ color: "var(--text2)", marginBottom: 20 }}>Block value vs. downscaled panchayat estimate, day by day.</p>

      <DemoDataBanner />

      {loading && <LoadingCard label="Loading panchayat forecasts…" />}
      {error && <ErrorCard message={error} />}

      {!loading && !error && forecast && (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
            {panchayats.map((p) => (
              <button key={p.panchayat_id} onClick={() => setSelectedId(p.panchayat_id)}
                style={{
                  padding: "8px 16px", borderRadius: 20, cursor: "pointer", fontSize: 13, fontWeight: 600,
                  border: `1.5px solid ${forecast.panchayat_id === p.panchayat_id ? "var(--green)" : "var(--border)"}`,
                  background: forecast.panchayat_id === p.panchayat_id ? "rgba(76,175,80,0.1)" : "transparent",
                  color: forecast.panchayat_id === p.panchayat_id ? "var(--green)" : "var(--text2)",
                }}>
                {p.panchayat_name}
              </button>
            ))}
          </div>

          <div className="card" style={{ padding: 22, marginBottom: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
              <MethodBadge method={forecast.method} />
              <SourceBadge source={forecast.block_source.source} isMocked={forecast.block_source.is_mocked} />
              <div style={{ display: "flex", gap: 6 }}>
                {VARIABLES.map((v) => (
                  <button key={v.key} onClick={() => setVariable(v)}
                    style={{
                      padding: "5px 10px", borderRadius: 20, fontSize: 11, cursor: "pointer",
                      border: `1.5px solid ${variable.key === v.key ? v.color : "var(--border)"}`,
                      background: variable.key === v.key ? `${v.color}18` : "transparent",
                      color: variable.key === v.key ? v.color : "var(--text2)", fontWeight: 600,
                    }}>
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
            <ComparisonTable forecast={forecast} variable={variable} />
          </div>

          <AdjustmentCard adjustment={forecast.adjustment} />
        </>
      )}
    </div>
  );
}
