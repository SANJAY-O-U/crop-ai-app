import { useCallback, useEffect, useState } from "react";
import { PILOT_BLOCK_ID, getBlock, getDownscaledForecastsForBlock, getPanchayats } from "./api";

// Shared data source for all CropCast screens: the pilot block, its panchayats,
// and each panchayat's downscaled forecast (which already carries the block's raw
// forecast as `block_source` for comparison).
//
// `reload()` re-runs the same three requests (used by the retry buttons in the
// error states). Existing callers are unaffected: the returned fields are a
// superset of the previous ones.
export function useBlockData(days = 5) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    loading: true, error: null, block: null, panchayats: [], forecasts: [], updatedAt: null,
  });

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    Promise.all([
      getBlock(PILOT_BLOCK_ID),
      getPanchayats(PILOT_BLOCK_ID),
      getDownscaledForecastsForBlock(PILOT_BLOCK_ID, days),
    ])
      .then(([block, panchayats, forecasts]) => {
        if (cancelled) return;
        setState({ loading: false, error: null, block, panchayats, forecasts, updatedAt: new Date() });
      })
      .catch((err) => {
        if (cancelled) return;
        setState((s) => ({ ...s, loading: false, error: err.message }));
      });

    return () => { cancelled = true; };
  }, [days, attempt]);

  return { ...state, reload };
}
