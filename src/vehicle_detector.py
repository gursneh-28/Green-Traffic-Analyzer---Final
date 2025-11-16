import cv2
import numpy as np
from ultralytics import YOLO
import os
import json

class VehicleDetector:
    def __init__(self, model_path='yolov8n.pt'):
        print("🚦 Initializing Vehicle Detector...")
        self.model = YOLO(model_path)
        self.vehicle_classes = ['car', 'truck', 'bus', 'motorcycle']
        print("✅ Vehicle Detector ready!")
    
    def detect_vehicles(self, image_path):
        """Detect vehicles in a single image and return count"""
        if not os.path.exists(image_path):
            print(f"❌ Image not found: {image_path}")
            return 0
        
        try:
            # Run YOLO inference
            results = self.model(image_path)
            
            vehicle_count = 0
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    class_id = int(box.cls[0])
                    class_name = self.model.names[class_id]
                    
                    # Count only vehicles
                    if class_name in self.vehicle_classes:
                        vehicle_count += 1
            
            return vehicle_count
            
        except Exception as e:
            print(f"❌ Error processing {image_path}: {e}")
            return 0
    
    def process_images_folder(self, folder_path):
        """Process all images in a folder and return counts"""
        counts = {}
        
        if not os.path.exists(folder_path):
            print(f"❌ Folder not found: {folder_path}")
            return counts
            
        for image_file in os.listdir(folder_path):
            if image_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_path = os.path.join(folder_path, image_file)
                count = self.detect_vehicles(image_path)
                counts[image_file] = count
                print(f"📊 Processed {image_file}: {count} vehicles")
        
        return counts

# Simple test
if __name__ == "__main__":
    detector = VehicleDetector()
    print("🚦 Vehicle detector created successfully!")