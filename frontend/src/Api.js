import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000", // backend
});

export const detectDisease = async (file) => {
  const formData = new FormData();
  formData.append("image", file);

  const res = await API.post("/api/v1/detect", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
};

export const getHistory = async () => {
  const res = await API.get("/api/v1/history");
  return res.data;
};

export const getMedicines = async (disease) => {
  const res = await API.get(`/api/v1/medicines?disease=${disease}`);
  return res.data;
};