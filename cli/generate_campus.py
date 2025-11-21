import json
import math

def generate_campus():
    nodes = []
    edges = []
    
    # Helper to add node
    def add_node(id, label, type, x, y, floor=0):
        nodes.append({
            "id": id,
            "label": label,
            "type": type,
            "floor": floor,
            "pos": [x, y, floor * 4.0] # Visual Z separation if needed, but we use floor index
        })

    # Helper to add edge
    def add_edge(u, v, length, width, cap=2.0, is_stairs=False):
        edges.append({
            "id": f"e_{u}_{v}",
            "from": u,
            "to": v,
            "length_m": length,
            "width_m": width,
            "capacity_pps": cap,
            "is_stairs": is_stairs
        })

    # --- Building A (Main Block) ---
    # Located at (0, 0) to (40, 0)
    
    # Main Entrance (Floor 0)
    add_node("ENTRY_MAIN", "Main Entrance", "entry", -15, 0, floor=0)
    add_edge("ENTRY_MAIN", "A_HALL_0_F0", 15.0, 4.0)
    add_edge("A_HALL_0_F0", "ENTRY_MAIN", 15.0, 4.0)

    # Hallway Spine - Floor 0
    for i in range(5):
        curr = f"A_HALL_{i}_F0"
        next_node = f"A_HALL_{i+1}_F0"
        add_node(curr, f"Hall A-{i} (G)", "junction", i * 12, 0, floor=0) # Spaced out to 12m
        
        if i < 4:
            add_edge(curr, next_node, 12.0, 3.0)
            add_edge(next_node, curr, 12.0, 3.0)
            
        # Classrooms (Top and Bottom)
        # Top
        rid = f"Class_A{i}_T_F0"
        add_node(rid, f"Class A{i}T (G)", "room", i * 12, 10, floor=0) # Moved to y=10
        add_edge(curr, rid, 8.0, 1.5)
        add_edge(rid, curr, 8.0, 1.5)
        
        # Bottom
        rid = f"Class_A{i}_B_F0"
        add_node(rid, f"Class A{i}B (G)", "room", i * 12, -10, floor=0) # Moved to y=-10
        add_edge(curr, rid, 8.0, 1.5)
        add_edge(rid, curr, 8.0, 1.5)

    # Hallway Spine - Floor 1
    for i in range(5):
        curr = f"A_HALL_{i}_F1"
        next_node = f"A_HALL_{i+1}_F1"
        add_node(curr, f"Hall A-{i} (1)", "junction", i * 12, 0, floor=1)
        
        if i < 4:
            add_edge(curr, next_node, 12.0, 3.0)
            add_edge(next_node, curr, 12.0, 3.0)
            
        # Classrooms (Top Only)
        rid = f"Class_A{i}_T_F1"
        add_node(rid, f"Class A{i}T (1)", "room", i * 12, 10, floor=1) # Moved to y=10
        add_edge(curr, rid, 8.0, 1.5)
        add_edge(rid, curr, 8.0, 1.5)
        
    # Library on Floor 1 (Bottom side, large)
    add_node("LIBRARY", "Library", "room", 24, -12, floor=1) # Moved to y=-12
    add_edge("A_HALL_2_F1", "LIBRARY", 10.0, 3.0)
    add_edge("LIBRARY", "A_HALL_2_F1", 10.0, 3.0)

    # Stairs in Building A (Ends of corridor)
    # Stairs 1: At Hall 0
    add_edge("A_HALL_0_F0", "A_HALL_0_F1", 8.0, 2.0, is_stairs=True) # Up
    add_edge("A_HALL_0_F1", "A_HALL_0_F0", 8.0, 2.0, is_stairs=True) # Down
    
    # Stairs 2: At Hall 4
    add_edge("A_HALL_4_F0", "A_HALL_4_F1", 8.0, 2.0, is_stairs=True) # Up
    add_edge("A_HALL_4_F1", "A_HALL_4_F0", 8.0, 2.0, is_stairs=True) # Down

    # Toilet in Building A (at end of Floor 0)
    # Moved to avoid collision with Class A4T (at 48, 10)
    add_node("WC_A", "Toilets A", "room", 48, 20, floor=0) 
    add_edge("A_HALL_4_F0", "WC_A", 12.0, 1.5)
    add_edge("WC_A", "A_HALL_4_F0", 12.0, 1.5)

    # --- Outdoor Path ---
    # Connects Building A (End) to Building B (Start)
    # Building B starts at (80, 30) to separate it more
    
    add_node("PATH_1", "Walkway 1", "junction", 60, 10, floor=0)
    add_node("PATH_2", "Walkway 2", "junction", 70, 20, floor=0)
    
    # A_HALL_4_F0 (48, 0) -> PATH_1 -> PATH_2 -> B_HALL_0
    add_edge("A_HALL_4_F0", "PATH_1", 15.0, 4.0) 
    add_edge("PATH_1", "A_HALL_4_F0", 15.0, 4.0)
    
    add_edge("PATH_1", "PATH_2", 15.0, 4.0)
    add_edge("PATH_2", "PATH_1", 15.0, 4.0)

    # --- Building B (Science Block) ---
    # Located at (80, 30) horizontal
    
    for i in range(4):
        curr = f"B_HALL_{i}"
        next_node = f"B_HALL_{i+1}"
        x_pos = 80 + (i * 12)
        y_pos = 30
        
        add_node(curr, f"Hall B-{i}", "junction", x_pos, y_pos, floor=0)
        
        if i == 0:
            # Connect to path
            add_edge("PATH_2", curr, 15.0, 4.0)
            add_edge(curr, "PATH_2", 15.0, 4.0)
            
        if i < 3:
            add_edge(curr, next_node, 12.0, 3.0)
            add_edge(next_node, curr, 12.0, 3.0)
            
        # Labs (Larger rooms, only on top side)
        lid = f"Lab_B{i}"
        add_node(lid, f"Lab B{i}", "room", x_pos, y_pos + 10, floor=0)
        add_edge(curr, lid, 10.0, 2.0)
        add_edge(lid, curr, 10.0, 2.0)

    # Toilet in Building B
    add_node("WC_B", "Toilets B", "room", 116, 22, floor=0) # Bottom side of last hall (30-8=22)
    add_edge("B_HALL_3", "WC_B", 8.0, 1.5)
    add_edge("WC_B", "B_HALL_3", 8.0, 1.5)

    # Exit Gate from Building B
    add_node("EXIT_SIDE", "Side Exit", "exit", 130, 30, floor=0)
    add_edge("B_HALL_3", "EXIT_SIDE", 15.0, 4.0)
    add_edge("EXIT_SIDE", "B_HALL_3", 15.0, 4.0)

    data = {
        "nodes": nodes,
        "edges": edges
    }
    
    with open("data/samples/floorplan_school.json", "w") as f:
        json.dump(data, f, indent=2)
        
    print(f"Generated campus with {len(nodes)} nodes and {len(edges)} edges.")

if __name__ == "__main__":
    generate_campus()
