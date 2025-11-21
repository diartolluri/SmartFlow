import json
import random

def generate_scenario():
    periods = []
    
    # Define Rooms
    classrooms_A_F0 = [f"Class_A{i}_T_F0" for i in range(5)] + [f"Class_A{i}_B_F0" for i in range(5)]
    classrooms_A_F1 = [f"Class_A{i}_T_F1" for i in range(5)] + ["LIBRARY"]
    labs_B = [f"Lab_B{i}" for i in range(4)]
    all_rooms = classrooms_A_F0 + classrooms_A_F1 + labs_B
    toilets = ["WC_A", "WC_B"]
    
    # 1. Morning Arrival (08:30 - 08:45)
    # 100 students enter from Main Entrance and go to random classrooms/labs
    movements_p1 = []
    
    for i in range(100):
        movements_p1.append({
            "population": "Student",
            "count": 1,
            "origin": "ENTRY_MAIN",
            "destination": random.choice(all_rooms)
        })
        
    periods.append({
        "id": "Morning Arrival",
        "start_time": "08:30",
        "end_time": "08:45",
        "movements": movements_p1
    })
    
    # 2. Lesson Change (09:45 - 10:00)
    # Move between rooms, some use toilets
    movements_p2 = []
    
    for i in range(100):
        start = random.choice(all_rooms)
        end = random.choice(all_rooms)
        while end == start:
            end = random.choice(all_rooms)
            
        # 20% chance to go to toilet
        if random.random() < 0.2:
            # Choose toilet based on start location (simple heuristic or random)
            # Let's just pick random for now, they might walk between buildings to pee!
            toilet = random.choice(toilets)
            chain_id = f"student_{i}"
            
            movements_p2.append({
                "population": "Mixed",
                "count": 1,
                "origin": start,
                "destination": toilet,
                "chain_id": chain_id
            })
            movements_p2.append({
                "population": "Mixed",
                "count": 1,
                "origin": toilet,
                "destination": end,
                "delay_s": 120,
                "chain_id": chain_id
            })
        else:
            movements_p2.append({
                "population": "Mixed",
                "count": 1,
                "origin": start,
                "destination": end
            })
        
    periods.append({
        "id": "Lesson Change 1",
        "start_time": "09:45",
        "end_time": "10:00",
        "movements": movements_p2
    })
    
    # 3. End of Day (15:00 - 15:15)
    # Everyone leaves via Side Exit or Main Entrance
    movements_p3 = []
    exits = ["ENTRY_MAIN", "EXIT_SIDE"]
    
    for i in range(100):
        start = random.choice(all_rooms)
        end = random.choice(exits)
        
        movements_p3.append({
            "population": "Student",
            "count": 1,
            "origin": start,
            "destination": end
        })
        
    periods.append({
        "id": "End of Day",
        "start_time": "15:00",
        "end_time": "15:15",
        "movements": movements_p3
    })

    data = {
        "name": "Campus Day",
        "random_seed": 123,
        "tick_seconds": 0.5,
        "transition_window_s": 900,
        "periods": periods,
        "behaviour": {
            "speed_base_mps": {"distribution": "normal", "mean": 1.3, "sigma": 0.3},
            "stairs_penalty": {"student": 2.0},
            "optimality_beta": {"value": 2.0},
            "detour_probability": {"value": 0.05},
            "reroute_interval_ticks": {"value": 20},
            "depart_jitter_s": {"uniform": [0, 60]}
        }
    }
    
    with open("data/samples/scenario_school.json", "w") as f:
        json.dump(data, f, indent=2)
        
    print("Generated scenario_school.json")

if __name__ == "__main__":
    generate_scenario()
