// ─── CropCast API client (Phase 1) ─────────────────────────────────────────────
// Kept separate from the existing CropAI fetch call in App.jsx on purpose —
// this file is only touched by the new CropCast screens, so nothing about the
// existing detect/result/medicine flow changes.

const API_URL = (() => {
  const env = import.meta.env.VITE_API_URL;
  if (env && env.trim() !== "") return env.trim().replace(/\/$/, "");
  return ""; // dev: Vite proxy forwards /api -> localhost:8000
})();

// Phase 1 supports exactly one pilot block — see backend/app/geospatial/seed_data.py
export const PILOT_BLOCK_ID = "BLOCK-DEMO-001";

async function getJSON(path) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`);
  } catch (err) {
    throw new Error(`Cannot reach the CropCast API (${err.message}). Is the backend running?`);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const j = await res.json(); detail = j.detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export const getBlock = (blockId = PILOT_BLOCK_ID) =>
  getJSON(`/api/v1/geospatial/blocks/${blockId}`);

export const getPanchayats = (blockId = PILOT_BLOCK_ID) =>
  getJSON(`/api/v1/geospatial/panchayats?block_id=${blockId}`);

export const getBlockForecast = (blockId = PILOT_BLOCK_ID, days = 7) =>
  getJSON(`/api/v1/weather/block/${blockId}/forecast?days=${days}`);

export const getDownscaledForecast = (panchayatId, days = 7) =>
  getJSON(`/api/v1/downscaling/${panchayatId}/forecast?days=${days}`);

export const getDownscaledForecastsForBlock = (blockId = PILOT_BLOCK_ID, days = 7) =>
  getJSON(`/api/v1/downscaling/block/${blockId}/forecast?days=${days}`);
