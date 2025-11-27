from flask import Flask
from ultralytics import YOLO

app = Flask(__name__)
model = YOLO("yolov8m.pt")  # hoặc tự tải từ ultralytics

@app.get("/")
def home():
    return "YOLOv8m running on Railway with Docker!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)