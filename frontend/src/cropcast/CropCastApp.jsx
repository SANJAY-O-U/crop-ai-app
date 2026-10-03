import { useState } from "react";
import CropCastDashboard from "./CropCastDashboard";
import MapExperience from "./MapExperience";
import PanchayatWeatherPage from "./PanchayatWeatherPage";
import WeatherMapPage from "./WeatherMapPage";

// Self-contained sub-app for the CropCast area. The map is the home screen:
// MAP → select Panchayat → weather + risk → graphs → advisory. The earlier
// dashboard, table and classic map screens remain reachable via onNavigate.
export default function CropCastApp({ onOpenCropHealth }) {
  const [page, setPage] = useState("explore");
  const [panchayatId, setPanchayatId] = useState(null);

  const navigate = (next, id = null) => {
    setPanchayatId(id);
    setPage(next === "map" ? "classic-map" : next === "home" ? "explore" : next);
  };

  if (page === "weather") return <PanchayatWeatherPage onNavigate={navigate} initialPanchayatId={panchayatId} />;
  if (page === "classic-map") return <WeatherMapPage onNavigate={navigate} />;
  if (page === "dashboard") return <CropCastDashboard onNavigate={navigate} />;
  return <MapExperience onNavigate={navigate} onOpenCropHealth={onOpenCropHealth} />;
}
