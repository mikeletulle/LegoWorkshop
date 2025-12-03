from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, UltrasonicSensor, ColorSensor
from pybricks.parameters import Port, Direction, Stop
from pybricks.tools import wait

hub = PrimeHub()

# Motors
left_motor = Motor(Port.C, positive_direction=Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.D, positive_direction=Direction.CLOCKWISE)

# Sensors
color_sensor = ColorSensor(Port.B)          # Down at board
distance_sensor = UltrasonicSensor(Port.F)  # Forward at box

# Scenario
scenario = "RECYCLING_OK"
print("STATUS:START scenario=" + scenario)

# ==========================================
# --- COLOR CALIBRATION VALUES (EDIT HERE) ---
# ==========================================
CAL_RED    = 5
CAL_GREEN  = 11
CAL_YELLOW = 13.5  # Range 13-15

# Filter out readings that are way off
VALID_RANGE_MIN = 0
VALID_RANGE_MAX = 25 

# ==========================================
# --- TUNABLE PARAMETERS ---
# ==========================================
DRIVE_SPEED = 200               # forward speed (deg/s)
SAMPLE_MS = 30                  # sensor sampling period (ms)
CONSECUTIVE_TARGET_HITS = 5     # Matches needed to confirm zone

# UPDATED: Increased to 150mm (~6 inches) to give more room to brake
STOP_DISTANCE_MM = 150          

# UPDATED: Increased to 500 degrees to drive deeper into the zone
FINAL_DRIVE_ANGLE = 500         

WARMUP_SAMPLES = 40             # Ignore sensor for first ~1.2s while driving

# Physical order on board: GREEN -> YELLOW -> RED
LINE_COLORS = ("GREEN", "YELLOW", "RED")

# Circular buffer for smoothing reflection
reflection_history = [0, 0, 0, 0, 0]


def stop_motors():
    left_motor.stop()
    right_motor.stop()


def drive_forward(speed=DRIVE_SPEED):
    left_motor.run(speed)
    right_motor.run(speed)


def spin_180():
    """Turn around in place, then continue."""
    print("STATUS:TURN_AROUND")
    left_motor.run_angle(300, 360, Stop.BRAKE, False)
    right_motor.run_angle(-300, 360, Stop.BRAKE, True)
    wait(200)


def get_smoothed_reflection():
    """
    Reads current reflection, updates history, returns (raw, avg).
    """
    raw = color_sensor.reflection()
    if raw is None: raw = 0
    
    reflection_history.pop(0)
    reflection_history.append(raw)
    
    avg = sum(reflection_history) / len(reflection_history)
    return raw, avg


def classify_zone_from_smoothed_ref(avg_ref):
    """
    Automatically finds the closest color based on CAL_ variables.
    """
    if avg_ref is None:
        return None
        
    if avg_ref < VALID_RANGE_MIN or avg_ref > VALID_RANGE_MAX:
        return None

    dist_red    = abs(avg_ref - CAL_RED)
    dist_green  = abs(avg_ref - CAL_GREEN)
    dist_yellow = abs(avg_ref - CAL_YELLOW)

    min_dist = min(dist_red, dist_green, dist_yellow)

    if min_dist == dist_red:
        return "RED"
    elif min_dist == dist_green:
        return "GREEN"
    elif min_dist == dist_yellow:
        return "YELLOW"
    
    return None


def choose_target_color_for_scenario(s: str):
    s = s.upper()
    if s == "RECYCLING_OK":
        return "GREEN"
    if s == "CONTAMINATED":
        return "RED"
    if s in ("INSPECTION", "URGENT_INSPECTION", "URGENT_FIELD_INSPECTION"):
        return "YELLOW"
    return "GREEN"


def main():
    global scenario

    print("Starting contamination sorter logic (Pre-Check + Safe Stop)...")
    print(f"DEBUG Config: RED={CAL_RED}, GREEN={CAL_GREEN}, YELLOW={CAL_YELLOW}")

    target_color = choose_target_color_for_scenario(scenario)
    print("STATUS:TARGET_COLOR=" + target_color)

    # 1. Initialize History Buffer
    wait(500)
    initial_val = color_sensor.reflection()
    if initial_val is None: initial_val = 0
    for i in range(5):
        reflection_history[i] = initial_val

    # ---------------------------------------------------------
    # NEW: PRE-CHECK (Are we already there?)
    # ---------------------------------------------------------
    # Check what zone we are sitting on RIGHT NOW.
    _, initial_avg = get_smoothed_reflection()
    start_zone = classify_zone_from_smoothed_ref(initial_avg)
    
    print(f"DEBUG: Start Read={initial_val}, Start Zone={start_zone}")

    if start_zone == target_color:
        print(f"DEBUG: Already on target {target_color}! Skipping drive.")
        print(f"{target_color} line reached (target {target_color})")
        print(f"STATUS:{target_color}_REACHED")
        
        # Determine status string
        if scenario.upper() == "RECYCLING_OK":
            print("STATUS:ZONE=RECYCLING_OK")
        elif scenario.upper() == "CONTAMINATED":
            print("STATUS:ZONE=CONTAMINATED")
        else:
            print("STATUS:ZONE=INSPECTION")
            
        hub.display.text("OK")
        print("STATUS:DONE")
        hub.speaker.beep(1500, 400)
        return  # EXIT PROGRAM HERE
    # ---------------------------------------------------------

    seen_yellow = False
    seen_green = False
    seen_red = False

    consecutive_target_hits = 0
    sample_counter = 0

    hub.display.text("GO")
    drive_forward(DRIVE_SPEED)

    while True:
        sample_counter += 1

        # 1. Get Sensor Data
        raw_refl, avg_refl = get_smoothed_reflection()
        current_zone = classify_zone_from_smoothed_ref(avg_refl)
        dist = distance_sensor.distance()

        # Debug print
        print(
            f"DEBUG Raw:{raw_refl} Avg:{avg_refl:.1f}",
            f"Zone:{current_zone}",
            f"Target:{target_color}",
            f"Hits:{consecutive_target_hits}"
        )

        # --- Safety: Obstacle Check (Increased Distance) ---
        if dist is not None and dist <= STOP_DISTANCE_MM:
            stop_motors()
            print(f"STATUS:ABORT_OBSTACLE distance_mm={dist}")
            hub.speaker.beep(400, 250)
            
            # Spin and Reset
            spin_180()
            seen_yellow = seen_green = seen_red = False
            consecutive_target_hits = 0
            
            # Reset warmup counter so we don't stop instantly after turning
            sample_counter = 0 
            
            drive_forward(DRIVE_SPEED)
            continue

        # --- Warmup (Skip detection while moving off start line) ---
        if sample_counter < WARMUP_SAMPLES:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # If detected zone is unknown, reset hits
        if current_zone not in LINE_COLORS:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # Mark crossed lines
        if current_zone == "YELLOW":
            seen_yellow = True
        elif current_zone == "GREEN":
            seen_green = True
        elif current_zone == "RED":
            seen_red = True

        # Check Target Matches
        if current_zone == target_color:
            consecutive_target_hits += 1
        else:
            consecutive_target_hits = 0

        # Success Logic
        if consecutive_target_hits >= CONSECUTIVE_TARGET_HITS:
            print("DEBUG: Sensor reached zone, moving rest of robot in")

            # Final push into the zone (Increased Angle)
            left_motor.run_angle(DRIVE_SPEED, FINAL_DRIVE_ANGLE, wait=False)
            right_motor.run_angle(DRIVE_SPEED, FINAL_DRIVE_ANGLE, wait=True)

            stop_motors()
            
            print(f"{current_zone} line reached (target {target_color})")
            print(f"STATUS:{current_zone}_REACHED")

            if scenario.upper() == "RECYCLING_OK":
                print("STATUS:ZONE=RECYCLING_OK")
            elif scenario.upper() == "CONTAMINATED":
                print("STATUS:ZONE=CONTAMINATED")
            else:
                print("STATUS:ZONE=INSPECTION")
            break

        # --- Wrong Way Logic (GREEN -> YELLOW -> RED) ---
        
        # Searching GREEN (Edge)
        if target_color == "GREEN":
            if current_zone == "YELLOW":
                pass
            elif current_zone == "RED" and seen_yellow and not seen_green:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_GREEN")
                spin_180()
                seen_yellow = seen_green = seen_red = False
                consecutive_target_hits = 0
                sample_counter = 0 # Reset warmup on turn
                drive_forward(DRIVE_SPEED)
                continue

        # Searching RED (Edge)
        if target_color == "RED":
            if current_zone == "YELLOW":
                pass
            elif current_zone == "GREEN" and seen_yellow and not seen_red:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_RED")
                spin_180()
                seen_yellow = seen_green = seen_red = False
                consecutive_target_hits = 0
                sample_counter = 0
                drive_forward(DRIVE_SPEED)
                continue

        # Searching YELLOW (Middle)
        if target_color == "YELLOW":
            if seen_green and seen_red and consecutive_target_hits == 0:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_YELLOW")
                spin_180()
                seen_yellow = seen_green = seen_red = False
                consecutive_target_hits = 0
                sample_counter = 0
                drive_forward(DRIVE_SPEED)
                continue

        wait(SAMPLE_MS)

    hub.display.text("OK")
    print("STATUS:DONE")
    hub.speaker.beep(1500, 400)


main()