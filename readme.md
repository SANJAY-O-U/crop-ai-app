🌱 AI-Powered Crop Disease Detection App
An AI-driven mobile application designed to help farmers detect crop diseases at an early stage using leaf image analysis. The system leverages Machine Learning (CNN) to classify crop diseases and provides instant treatment and prevention recommendations.

This project focuses on solving real-world agricultural challenges in India.

🚜 Problem Statement
Farmers often face heavy crop losses due to late or incorrect identification of crop diseases. Limited access to agricultural experts and dependency on traditional methods result in improper pesticide usage and reduced yield.

💡 Solution
The application allows farmers to capture or upload images of infected crop leaves. These images are analyzed using a trained AI model, which identifies the disease and suggests appropriate remedies and preventive measures.

🌱 AI-Based Crop Disease Detection System
📌 Overview
This project is an AI-powered web application that detects crop diseases from leaf images using Deep Learning and Computer Vision techniques.

🚀 Features
Multi-crop support (Tomato, Potato, Pepper)
Leaf detection using YOLO
Disease classification using CNN (ResNet)
Explainable AI using Grad-CAM
Confidence-based decision system
Web-based interface (React + FastAPI)
🛠 Tech Stack
Frontend: React (Vite) Backend: FastAPI (Python) AI Models: PyTorch, YOLOv8 Explainability: Grad-CAM

📂 Project Structure
crop-ai-app/ │ ├── backend/ │ ├── app/ │ │ ├── main.py │ │ ├── model/ │ │ │ ├── model.py │ │ │ ├── predict.py │ │ │ └── crop_model.pth │ │ ├── utils/ │ │ │ └── image_utils.py │ │ └── routes/ │ │ └── detect.py │ ├── requirements.txt │ └── train_model.py │ ├── frontend/ │ ├── src/ │ │ ├── App.jsx │ │ ├── api.js │ │ └── main.jsx │ ├── index.html │ └── package.json │ └── README.md