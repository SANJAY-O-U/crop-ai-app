import { useCallback, useEffect, useRef, useState } from "react";

// Reactive window.matchMedia — used to choose between the mobile bottom sheet
// and the desktop side panel without duplicating the component tree in CSS.
export function useMediaQuery(query) {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

const GEO_MESSAGES = {
  denied: "Location permission is turned off. Allow it in your browser settings to see where you are on the map.",
  timeout: "Finding your location took too long. Try again.",
  unavailable: "Your location couldn't be determined on this device.",
  unsupported: "This browser can't share your location.",
};

// Browser geolocation with every failure state surfaced (never silently ignored).
// status: idle | locating | ready | denied | timeout | unavailable | unsupported
export function useGeolocation() {
  const [state, setState] = useState({ status: "idle", position: null, message: null });
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const locate = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setState({ status: "unsupported", position: null, message: GEO_MESSAGES.unsupported });
      return;
    }
    setState((s) => ({ ...s, status: "locating", message: null }));
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (!alive.current) return;
        setState({
          status: "ready",
          position: { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy },
          message: null,
        });
      },
      (err) => {
        if (!alive.current) return;
        const status = err.code === 1 ? "denied" : err.code === 3 ? "timeout" : "unavailable";
        setState({ status, position: null, message: GEO_MESSAGES[status] });
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }, []);

  const dismiss = useCallback(() => setState((s) => (s.status === "ready" ? s : { ...s, status: "idle", message: null })), []);

  return { ...state, locate, dismiss };
}
