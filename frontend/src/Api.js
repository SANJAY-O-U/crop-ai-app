export async function detectDisease(imageFile, crop) {
  const formData = new FormData();
  formData.append("file", imageFile);
  formData.append("crop", crop);

  const response = await fetch("http://127.0.0.1:8000/detect", {
    method: "POST",
    body: formData
  });

  if (!response.ok) {
    throw new Error("Detection failed");
  }

  return response.json();
}
