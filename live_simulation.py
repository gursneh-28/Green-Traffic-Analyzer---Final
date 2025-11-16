import os
import sys
import time
import threading
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from signal_controller import TrafficSignalController
from vehicle_detector import VehicleDetector
from dashboard import dashboard, run_dashboard

def run_traffic_simulation():
    """Run the traffic simulation with PROPER timing"""
    controller = TrafficSignalController()
    
    print("🚦 Starting Live Traffic Simulation with PROPER Timing")
    print("=" * 60)
    
    # Test scenarios
    test_scenarios = [
        {'camera_1': 25, 'camera_2': 8, 'camera_3': 15, 'camera_4': 12},
        {'camera_1': 18, 'camera_2': 22, 'camera_3': 10, 'camera_4': 8},
        {'camera_1': 30, 'camera_2': 5, 'camera_3': 20, 'camera_4': 15}
    ]
    
    scenario_index = 0
    
    try:
        while True:
            # Cycle through test scenarios
            vehicle_counts = test_scenarios[scenario_index]
            scenario_index = (scenario_index + 1) % len(test_scenarios)
            
            print(f"\n🎯 New Scenario: {vehicle_counts}")
            print("Calculating optimal signal timing...")
            
            # Get the signal sequence with ACTUAL calculated times
            sequence = controller.get_next_signal_sequence(vehicle_counts)
            
            # Display each phase with PROPER timing
            for i, phase in enumerate(sequence):
                camera = phase['camera']
                green_time = phase['green_time']  # ACTUAL calculated time (15-45s)
                total_phase_time = phase['phase_time']
                
                print(f"\n🚥 PHASE {i+1}: {camera.upper()} - 🟢 GREEN for {green_time}s")
                print(f"   Vehicles: {phase['vehicle_count']} | Total phase: {total_phase_time}s")
                
                # Show GREEN light for ACTUAL calculated time
                for second in range(green_time):
                    dashboard.update_data(
                        vehicle_counts=vehicle_counts,
                        current_green=camera,
                        efficiency=controller.calculate_efficiency(vehicle_counts, sequence)
                    )
                    if second % 5 == 0:  # Print every 5 seconds
                        print(f"   🟢 {green_time - second}s remaining...")
                    time.sleep(1)
                
                # Show YELLOW transition (4 seconds as per controller)
                print(f"   🟡 YELLOW for 4s")
                for second in range(4):
                    dashboard.update_data(
                        vehicle_counts=vehicle_counts,
                        current_green=f"{camera} (YELLOW)",
                        efficiency=controller.calculate_efficiency(vehicle_counts, sequence)
                    )
                    time.sleep(1)
                
                # Show ALL RED safety buffer (1 second) ONLY between phases
                if i < len(sequence) - 1:  # Not after the last phase
                    print(f"   🔴 ALL RED for 1s (safety buffer)")
                    dashboard.update_data(
                        vehicle_counts=vehicle_counts,
                        current_green="ALL RED",
                        efficiency=controller.calculate_efficiency(vehicle_counts, sequence)
                    )
                    time.sleep(1)
            
            # Calculate and display cycle efficiency
            efficiency = controller.calculate_efficiency(vehicle_counts, sequence)
            print(f"\n✅ Cycle completed | Efficiency: {efficiency:.1f}%")
            
            # Brief pause between cycles (keep last signal green)
            dashboard.update_data(
                vehicle_counts=vehicle_counts,
                current_green=sequence[-1]['camera'],  # Keep last camera green
                efficiency=efficiency
            )
            print("🔄 Next cycle starting in 5 seconds...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped")

def main():
    # Start dashboard in a separate thread
    dashboard_thread = threading.Thread(target=run_dashboard)
    dashboard_thread.daemon = True
    dashboard_thread.start()
    
    # Wait a moment for dashboard to start
    time.sleep(2)
    
    # Start traffic simulation
    run_traffic_simulation()

if __name__ == '__main__':
    main()