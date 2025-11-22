"""
Generates a custom floorplan based on the user's sketch.
- Building 1 (Left): 4 Classrooms, H-style corridor.
- Building 2 (Right): 5 Classrooms, 1 Toilet, Spine corridor.
- Outdoor paths connecting them.
"""

import json
import math
from pathlib import Path

OUTPUT_DIR = Path("data/samples")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def generate():
    nodes = []
    edges = []

    # --- Building 1 (Left) ---
    # Center X ~ 40
    # Corridors
    nodes.append({"id": "b1_c_top", "label": "", "type": "junction", "floor": 0, "pos": [40, 60, 0]})
    nodes.append({"id": "b1_c_bot", "label": "", "type": "junction", "floor": 0, "pos": [40, 40, 0]})
    
    # Classrooms (Red dots)
    nodes.append({"id": "b1_r1", "label": "C1", "type": "room", "floor": 0, "pos": [25, 60, 0]})
    nodes.append({"id": "b1_r2", "label": "C2", "type": "room", "floor": 0, "pos": [55, 60, 0]})
    nodes.append({"id": "b1_r3", "label": "C3", "type": "room", "floor": 0, "pos": [25, 40, 0]})
    nodes.append({"id": "b1_r4", "label": "C4", "type": "room", "floor": 0, "pos": [55, 40, 0]})

    # Edges B1
    # Spine
    edges.append({"id": "e_b1_spine", "from": "b1_c_top", "to": "b1_c_bot", "length_m": 20, "width_m": 3.0, "capacity_pps": 2.0})
    # Rooms
    edges.append({"id": "e_b1_r1", "from": "b1_c_top", "to": "b1_r1", "length_m": 15, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b1_r2", "from": "b1_c_top", "to": "b1_r2", "length_m": 15, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b1_r3", "from": "b1_c_bot", "to": "b1_r3", "length_m": 15, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b1_r4", "from": "b1_c_bot", "to": "b1_r4", "length_m": 15, "width_m": 2.0, "capacity_pps": 1.5})


    # --- Building 2 (Right) ---
    # Center X ~ 120
    # Corridors (Spine)
    nodes.append({"id": "b2_c_top", "label": "", "type": "junction", "floor": 0, "pos": [120, 70, 0]})
    nodes.append({"id": "b2_c_mid", "label": "", "type": "junction", "floor": 0, "pos": [120, 50, 0]})
    nodes.append({"id": "b2_c_bot", "label": "", "type": "junction", "floor": 0, "pos": [120, 30, 0]})

    # Classrooms (Red dots) & Toilet (Purple dot)
    # Top Row
    nodes.append({"id": "b2_r1", "label": "C5", "type": "room", "floor": 0, "pos": [100, 70, 0]})
    nodes.append({"id": "b2_r2", "label": "C6", "type": "room", "floor": 0, "pos": [140, 70, 0]})
    # Mid Row
    nodes.append({"id": "b2_r3", "label": "C7", "type": "room", "floor": 0, "pos": [100, 50, 0]})
    nodes.append({"id": "b2_r4", "label": "C8", "type": "room", "floor": 0, "pos": [140, 50, 0]})
    # Bot Row
    nodes.append({"id": "b2_t1", "label": "WC", "type": "toilet", "floor": 0, "pos": [100, 30, 0]}) # Purple/Grey dot
    nodes.append({"id": "b2_r5", "label": "C9", "type": "room", "floor": 0, "pos": [140, 30, 0]})

    # Edges B2
    # Spine
    edges.append({"id": "e_b2_spine1", "from": "b2_c_top", "to": "b2_c_mid", "length_m": 20, "width_m": 3.0, "capacity_pps": 2.0})
    edges.append({"id": "e_b2_spine2", "from": "b2_c_mid", "to": "b2_c_bot", "length_m": 20, "width_m": 3.0, "capacity_pps": 2.0})
    
    # Rooms
    edges.append({"id": "e_b2_r1", "from": "b2_c_top", "to": "b2_r1", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b2_r2", "from": "b2_c_top", "to": "b2_r2", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b2_r3", "from": "b2_c_mid", "to": "b2_r3", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b2_r4", "from": "b2_c_mid", "to": "b2_r4", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b2_t1", "from": "b2_c_bot", "to": "b2_t1", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})
    edges.append({"id": "e_b2_r5", "from": "b2_c_bot", "to": "b2_r5", "length_m": 20, "width_m": 2.0, "capacity_pps": 1.5})


    # --- Outdoor Paths ---
    # Path 1: B1 Top -> B2 Mid (Curved-ish)
    # We add a waypoint to make it look like the sketch
    nodes.append({"id": "path_waypoint_1", "label": "", "type": "junction", "floor": 0, "pos": [80, 55, 0]})
    
    edges.append({"id": "e_path1_a", "from": "b1_c_top", "to": "path_waypoint_1", "length_m": 40, "width_m": 4.0, "capacity_pps": 3.0})
    edges.append({"id": "e_path1_b", "from": "path_waypoint_1", "to": "b2_c_mid", "length_m": 40, "width_m": 4.0, "capacity_pps": 3.0})

    # Path 2: B1 Bot -> B2 Bot (Curved-ish)
    nodes.append({"id": "path_waypoint_2", "label": "", "type": "junction", "floor": 0, "pos": [80, 35, 0]})
    
    edges.append({"id": "e_path2_a", "from": "b1_c_bot", "to": "path_waypoint_2", "length_m": 40, "width_m": 4.0, "capacity_pps": 3.0})
    edges.append({"id": "e_path2_b", "from": "path_waypoint_2", "to": "b2_c_bot", "length_m": 40, "width_m": 4.0, "capacity_pps": 3.0})


    # Construct final object
    floorplan = {
        "nodes": nodes,
        "edges": edges
    }

    output_path = OUTPUT_DIR / "floorplan_custom.json"
    with open(output_path, "w") as f:
        json.dump(floorplan, f, indent=2)
    
    print(f"Generated custom floorplan at {output_path}")

if __name__ == "__main__":
    generate()
