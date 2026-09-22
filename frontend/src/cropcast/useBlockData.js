import { useEffect, useState } from "react";
import { PILOT_BLOCK_ID, getBlock, getDownscaledForecastsForBlock, getPanchayats } from "./api";

// Shared data source for all three CropCast Phase 1 screens: the pilot
// block, its panchayats, and each panchayat's downscaled forecast (which
// already carries the block's raw forecast as `block_source` for comparison).
export function useBlockData(days = 5) {
  const [state, setState] = useState({
    loading: true, error: null, block: null, panchayats: [], forecasts: [],
  });

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
        setState({ loading: false, error: null, block, panchayats, forecasts });
      })
      .catch((err) => {
        if (cancelled) return;
        setState((s) => ({ ...s, loading: false, error: err.message }));
      });

    return () => { cancelled = true; };
  }, [days]);

  return state;
}
