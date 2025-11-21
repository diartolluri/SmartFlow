import json
import math

def generate_school():
    nodes = []
    edges = []
    
    # Helper to add node
    def add_node(id, label, type, x, y):
        nodes.append({
            "id": id,
            "label": label,
            "type": type,
            "floor": 0,
            "pos": [x, y, 0]
        })

    # Helper to add edge (bi-directional by default in our new logic, but let's be explicit for main corridors)
    def add_edge(u, v, length, width, cap=2.0):
        edges.append({
            "id": f"e_{u}_{v}",
            "from": u,
            "to": v,
            "length_m": length,
            "width_m": width,
            "capacity_pps": cap
        })

    # 1. Main Corridor (Spine) - 50m long
    # Nodes M0 to M5 spaced 10m apart
    for i in range(6):
        add_node(f"M{i}", f"Main Hall {i}", "junction", i * 10, 0)
        if i > 0:
            add_edge(f"M{i-1}", f"M{i}", 10.0, 3.0, 4.0)
            add_edge(f"M{i}", f"M{i-1}", 10.0, 3.0, 4.0)

    # 2. Classrooms along Main Corridor
    # 2 rooms per junction (Top and Bottom)
    room_count = 0
    for i in range(6):
        # Top Room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", i * 10, 5)
        add_edge(f"M{i}", rid, 5.0, 1.5, 2.0) # Entrance
        add_edge(rid, f"M{i}", 5.0, 1.5, 2.0) # Exit
        room_count += 1
        
        # Bottom Room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", i * 10, -5)
        add_edge(f"M{i}", rid, 5.0, 1.5, 2.0)
        add_edge(rid, f"M{i}", 5.0, 1.5, 2.0)
        room_count += 1

    # 3. Left Wing (at M1) - Vertical
    # Nodes L1, L2 going up
    add_node("L1", "Left Wing 1", "junction", 10, 10)
    add_node("L2", "Left Wing 2", "junction", 10, 20)
    
    add_edge("M1", "L1", 10.0, 2.5, 3.0)
    add_edge("L1", "M1", 10.0, 2.5, 3.0)
    add_edge("L1", "L2", 10.0, 2.5, 3.0)
    add_edge("L2", "L1", 10.0, 2.5, 3.0)
    
    # Rooms on Left Wing
    for j, node in enumerate(["L1", "L2"]):
        # Left side room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", 5, 10 * (j+1))
        add_edge(node, rid, 5.0, 1.5, 2.0)
        add_edge(rid, node, 5.0, 1.5, 2.0)
        room_count += 1
        
        # Right side room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", 15, 10 * (j+1))
        add_edge(node, rid, 5.0, 1.5, 2.0)
        add_edge(rid, node, 5.0, 1.5, 2.0)
        room_count += 1

    # 4. Right Wing (at M4) - Vertical
    # Nodes RW1, RW2 going down
    add_node("RW1", "Right Wing 1", "junction", 40, -10)
    add_node("RW2", "Right Wing 2", "junction", 40, -20)
    
    add_edge("M4", "RW1", 10.0, 2.5, 3.0)
    add_edge("RW1", "M4", 10.0, 2.5, 3.0)
    add_edge("RW1", "RW2", 10.0, 2.5, 3.0)
    add_edge("RW2", "RW1", 10.0, 2.5, 3.0)
    
    # Rooms on Right Wing
    for j, node in enumerate(["RW1", "RW2"]):
        # Left side room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", 35, -10 * (j+1))
        add_edge(node, rid, 5.0, 1.5, 2.0)
        add_edge(rid, node, 5.0, 1.5, 2.0)
        room_count += 1
        
        # Right side room
        rid = f"R{room_count}"
        add_node(rid, f"Room {room_count}", "room", 45, -10 * (j+1))
        add_edge(node, rid, 5.0, 1.5, 2.0)
        add_edge(rid, node, 5.0, 1.5, 2.0)
        room_count += 1

    # Total rooms so far: 12 (Main) + 4 (Left) + 4 (Right) = 20.
    # Let's add a "Gym" and "Cafeteria" at the ends.
    
    # Gym at M0 (Left end)
    add_node("GYM", "Gymnasium", "room", -10, 0)
    add_edge("M0", "GYM", 10.0, 4.0, 5.0)
    add_edge("GYM", "M0", 10.0, 4.0, 5.0)
    
    # Cafeteria at M5 (Right end)
    add_node("CAFE", "Cafeteria", "room", 60, 0)
    add_edge("M5", "CAFE", 10.0, 4.0, 5.0)
    add_edge("CAFE", "M5", 10.0, 4.0, 5.0)
    
    # 5. Toilets
    # Toilet Block A near M2
    add_node("WC_A", "Toilets A", "room", 20, 8)
    add_edge("M2", "WC_A", 8.0, 2.0, 3.0)
    add_edge("WC_A", "M2", 8.0, 2.0, 3.0)
    
    # Toilet Block B near M3
    add_node("WC_B", "Toilets B", "room", 30, -8)
    add_edge("M3", "WC_B", 8.0, 2.0, 3.0)
    add_edge("WC_B", "M3", 8.0, 2.0, 3.0)
    
    data = {
        "metadata": {"name": "Comprehensive School Layout", "version": 1},
        "nodes": nodes,
        "edges": edges
    }
    
    with open("data/samples/floorplan_school.json", "w") as f:
        json.dump(data, f, indent=2)
        
    print(f"Generated school with {len(nodes)} nodes and {len(edges)} edges.")

if __name__ == "__main__":
    generate_school()
