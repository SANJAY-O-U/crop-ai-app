import { useState } from "react";
import CropCastDashboard from "./CropCastDashboard";
import PanchayatWeatherPage from "./PanchayatWeatherPage";
import WeatherMapPage from "./WeatherMapPage";

// Self-contained sub-app for the new CropCast area — mounted from the
// existing App.jsx behind one nav entry, so the existing CropAI page-switch
// logic in App.jsx doesn't need to know about CropCast's internal screens.
export default function CropCastApp() {
  const [page, setPage] = useState("dashboard");

  if (page === "weather") return <PanchayatWeatherPage onNavigate={setPage} />;
  if (page === "map") return <WeatherMapPage onNavigate={setPage} />;
  return <CropCastDashboard onNavigate={setPage} />;
}
