import React, { useState } from "react";
import { detectDisease } from "./api";
import "./index.css";

function App() {
  const [crop, setCrop] = useState("tomato");
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setImage(file);
    setPreview(URL.createObjectURL(file));
    setResult(null);
  };

  const handleDetect = async () => {
    if (!image) {
      alert("Please select an image");
      return;
    }

    try {
      setLoading(true);
      const data = await detectDisease(image, crop);
      setResult(data);
    } catch (err) {
      alert("Error detecting disease");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
const videoRef = React.useRef(null);
const canvasRef = React.useRef(null);

const startCamera = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  videoRef.current.srcObject = stream;
};

const capturePhoto = () => {
  const canvas = canvasRef.current;
  const video = videoRef.current;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0);

  canvas.toBlob((blob) => {
    const file = new File([blob], "camera.jpg", { type: "image/jpeg" });
    setImage(file);
    setPreview(URL.createObjectURL(blob));
  });
};

  return (
    <div className="container">
      <h1>🌱 AI Crop Disease Detector</h1>

      {/* Crop Selector */}
      <select value={crop} onChange={(e) => setCrop(e.target.value)}>
        <option value="tomato">Tomato</option>
        <option value="potato">Potato</option>
        <option value="pepper">Pepper</option>
      </select>

      {/* Image Upload */}
      <input type="file" accept="image/*" onChange={handleImageChange} />
<button onClick={startCamera}>📷 Open Camera</button>

<video ref={videoRef} autoPlay className="preview" />

<button onClick={capturePhoto}>📸 Capture</button>

<canvas ref={canvasRef} style={{ display: "none" }} />

      {/* Original Image Preview */}
      {preview && (
        <>
          <h4>Original Image</h4>
          <img src={preview} alt="Original" className="preview" />
        </>
      )}

      {/* Detect Button */}
      <button onClick={handleDetect} disabled={loading}>
        {loading ? "Detecting..." : "Detect Disease"}
      </button>


      {/* Results */}
      {result && (
        <div className="result">
          {result.status === "success" && (
            <>
              <h2>🦠 Crop: {result.crop}</h2>
              <h3>Disease: {result.disease}</h3>
              <p><b>Confidence:</b> {result.confidence}%</p>
            </>
          )}

          {result.status === "warning" && (
            <>
              <h3>⚠️ {result.message}</h3>
            </>
          )}

          {result.top_predictions && (
            <>
              <h4>Top Predictions</h4>
              <ul>
                {result.top_predictions.map((p, i) => (
                  <li key={i}>
                    {p.label} — {p.confidence}%
                  </li>
                ))}
              </ul>
            </>
          )}
          {result?.boxed_image && (
  <>
    <h4>YOLO Leaf Detection</h4>
    <img
      src={`data:image/jpeg;base64,${result.boxed_image}`}
      alt="YOLO Detection"
      className="preview"
    />
  </>
)}

          {result?.grad_cam && (
  <>
    <h4>Grad-CAM (Disease Focus)</h4>
    <img
      src={`data:image/jpeg;base64,${result.grad_cam}`}
      alt="Grad CAM"
      className="preview"
    />
  </>
)}      
        </div>
      )}
    </div>
  );
}

export default App;
