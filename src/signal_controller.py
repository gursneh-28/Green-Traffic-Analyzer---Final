import time
import json
from datetime import datetime

class TrafficSignalController:
    def __init__(self):
        # Realistic signal timing parameters (in seconds)
        self.total_cycle_time = 90      # Fixed 90-second total cycle
        self.min_green_time = 15        # Safety minimum
        self.max_green_time = 45        # Efficiency maximum
        self.yellow_time = 4            # Standard yellow time
        self.all_red_time = 1           # Safety buffer between phases
        
        # Current signal state
        self.current_green = None
        self.signal_start_time = 0
        self.cycle_data = []
        
        print("🚦 Traffic Signal Controller Initialized!")
        print(f"   Total Cycle: {self.total_cycle_time}s | Green Range: {self.min_green_time}-{self.max_green_time}s")
    
    def calculate_green_times(self, camera_counts):
        """Calculate green times with fixed 90-second total cycle"""
        num_cameras = len(camera_counts)
        total_vehicles = sum(camera_counts.values())
        
        if total_vehicles == 0:
            # Equal time when no traffic
            equal_time = self.total_cycle_time // num_cameras
            return {cam: max(self.min_green_time, min(self.max_green_time, equal_time)) 
                   for cam in camera_counts.keys()}
        
        # Calculate available green time (total cycle - overhead)
        overhead_per_phase = self.yellow_time + self.all_red_time
        total_overhead = num_cameras * overhead_per_phase
        available_green_time = self.total_cycle_time - total_overhead
        
        # First pass: calculate proportional green times
        green_times = {}
        for camera, count in camera_counts.items():
            ratio = count / total_vehicles
            green_time = available_green_time * ratio
            green_times[camera] = green_time
        
        # Second pass: apply min/max limits
        limited_times = {}
        for camera, green_time in green_times.items():
            limited_time = max(self.min_green_time, min(self.max_green_time, green_time))
            limited_times[camera] = limited_time
        
        # Third pass: adjust if total exceeds available green time
        total_calculated = sum(limited_times.values())
        if total_calculated > available_green_time:
            # Scale down proportionally
            scale_factor = available_green_time / total_calculated
            for camera in limited_times:
                limited_times[camera] = round(limited_times[camera] * scale_factor)
                # Ensure minimum after scaling
                limited_times[camera] = max(self.min_green_time, limited_times[camera])
        else:
            # Round to integers
            for camera in limited_times:
                limited_times[camera] = round(limited_times[camera])
        
        return limited_times
    
    def get_next_signal_sequence(self, camera_counts):
        """Determine the optimal signal sequence (busiest first)"""
        green_times = self.calculate_green_times(camera_counts)
        
        # Sort cameras by vehicle count (descending) - busiest goes first
        sorted_cameras = sorted(camera_counts.items(), key=lambda x: x[1], reverse=True)
        
        sequence = []
        for camera, count in sorted_cameras:
            sequence.append({
                'camera': camera,
                'green_time': green_times[camera],
                'vehicle_count': count,
                'phase_time': green_times[camera] + self.yellow_time + self.all_red_time
            })
        
        return sequence
    
    def simulate_signal_cycle(self, camera_counts):
        """Simulate one complete signal cycle with realistic timing"""
        print(f"\n🔄 Starting Signal Cycle at {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 50)
        
        sequence = self.get_next_signal_sequence(camera_counts)
        
        # Calculate actual total cycle time
        total_cycle_time = sum(phase['phase_time'] for phase in sequence)
        
        cycle_info = {
            'timestamp': datetime.now().isoformat(),
            'camera_counts': camera_counts,
            'sequence': sequence,
            'total_cycle_time': total_cycle_time,
            'efficiency': self.calculate_efficiency(camera_counts, sequence)
        }
        
        print(f"📊 Vehicle Distribution: {camera_counts}")
        print(f"⏱️  Expected Cycle Time: {total_cycle_time}s")
        
        # Simulate each phase
        for i, phase in enumerate(sequence):
            camera = phase['camera']
            green_time = phase['green_time']
            vehicle_count = phase['vehicle_count']
            
            print(f"\n🚥 PHASE {i+1}: {camera.upper()} - 🟢 GREEN")
            print(f"   Vehicles waiting: {vehicle_count}")
            print(f"   Green time: {green_time} seconds")
            
            # Simulate green light (no actual sleep for demo)
            # In real system: time.sleep(green_time)
            
            # Yellow light transition
            print(f"   🟡 YELLOW for {self.yellow_time} seconds")
            # In real system: time.sleep(self.yellow_time)
            
            # All red safety buffer
            print(f"   🔴 ALL RED for {self.all_red_time} seconds")
            # In real system: time.sleep(self.all_red_time)
            
            print(f"   ✅ Phase completed: {phase['phase_time']} seconds total")
        
        print(f"\n✅ Cycle completed in {total_cycle_time} seconds")
        print(f"📈 Cycle Efficiency: {cycle_info['efficiency']:.1f}%")
        
        self.cycle_data.append(cycle_info)
        return cycle_info
    
    def calculate_efficiency(self, camera_counts, sequence):
        """Calculate timing efficiency compared to fixed system"""
        total_vehicles = sum(camera_counts.values())
        
        if total_vehicles == 0:
            return 100.0
        
        # Our adaptive system waiting time
        adaptive_waiting = 0
        for phase in sequence:
            camera = phase['camera']
            count = camera_counts[camera]
            # Vehicles wait during other phases
            other_phases_time = sum(p['phase_time'] for p in sequence if p['camera'] != camera)
            adaptive_waiting += count * other_phases_time
        
        # Fixed system waiting time (equal 22.5s green for each)
        fixed_green = 22.5  # 90s total / 4 cameras
        fixed_phase_time = fixed_green + self.yellow_time + self.all_red_time
        fixed_waiting = 0
        for count in camera_counts.values():
            fixed_waiting += count * (3 * fixed_phase_time)  # Wait during other 3 phases
        
        if fixed_waiting == 0:
            return 100.0
        
        efficiency = (1 - (adaptive_waiting / fixed_waiting)) * 100
        return max(0, min(100, efficiency))  # Cap between 0-100%
    
    def print_cycle_summary(self, cycle_info):
        """Print detailed summary of a signal cycle"""
        print(f"\n📋 CYCLE SUMMARY:")
        print(f"   Timestamp: {cycle_info['timestamp']}")
        print(f"   Total Cycle Time: {cycle_info['total_cycle_time']}s")
        print(f"   Efficiency: {cycle_info['efficiency']:.1f}%")
        
        print(f"\n   Phase Details:")
        for i, phase in enumerate(cycle_info['sequence']):
            print(f"   {i+1}. {phase['camera']}: {phase['vehicle_count']} vehicles → "
                  f"{phase['green_time']}s green (+{self.yellow_time}s yellow + {self.all_red_time}s red)")