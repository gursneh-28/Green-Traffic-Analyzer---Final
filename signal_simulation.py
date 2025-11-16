import os
import sys
import json
from datetime import datetime

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("🚦 Starting Traffic Signal Simulation with REAL Image Processing")
    print("=" * 60)
    
    try:
        from signal_controller import TrafficSignalController
        from vehicle_detector import VehicleDetector
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    # Initialize systems
    controller = TrafficSignalController()
    detector = VehicleDetector()
    
    print("📊 Running Simulation with ACTUAL Vehicle Detection")
    print("=" * 60)
    
    # Create results folder
    os.makedirs('results', exist_ok=True)
    
    # Test with actual images from your dataset
    test_scenarios = [
        {'folder': 'data/0', 'name': 'Timeframe 0s'},  # Your actual images
        {'folder': 'data/5', 'name': 'Timeframe 5s'}   # Your actual images
    ]
    
    for scenario in test_scenarios:
        folder_path = scenario['folder']
        scenario_name = scenario['name']
        
        if not os.path.exists(folder_path):
            print(f"❌ Folder not found: {folder_path}")
            continue
            
        print(f"\n🎯 PROCESSING: {scenario_name} from {folder_path}")
        print("-" * 50)
        
        # Detect vehicles in actual images
        vehicle_counts = {}
        image_files = [f for f in os.listdir(folder_path) if f.endswith(('.jpg', '.png'))]
        
        # Process first 4 images as our 4 cameras
        for i, image_file in enumerate(image_files[:4], 1):
            image_path = os.path.join(folder_path, image_file)
            count = detector.detect_vehicles(image_path)
            vehicle_counts[f'camera_{i}'] = count
            print(f"   📷 {image_file}: {count} vehicles")
        
        # Run signal cycle with REAL detected counts
        if vehicle_counts:
            cycle_info = controller.simulate_signal_cycle(vehicle_counts)
            print(f"📈 Cycle Efficiency: {cycle_info['efficiency']:.1f}%")
        
        # Save results
        with open('results/signal_cycles.json', 'w') as f:
            json.dump(controller.cycle_data, f, indent=2)
    
    print(f"\n✅ Simulation completed! Processed {len(controller.cycle_data)} scenarios")
    print("💾 Results saved to: results/signal_cycles.json")

if __name__ == "__main__":
    main()