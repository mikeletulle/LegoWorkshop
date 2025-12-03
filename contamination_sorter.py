from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, UltrasonicSensor, ColorSensor
from pybricks.parameters import Port, Direction, Stop, Color
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

# --- Tunable parameters ---

DRIVE_SPEED = 200               # forward speed (deg/s)
SAMPLE_MS = 30                  # sensor sampling period (ms)
CONSECUTIVE_TARGET_HITS = 5     # Matches needed to confirm zone
STOP_DISTANCE_MM = 100          # distance to stop before box
FINAL_DRIVE_ANGLE = 360         # Degrees to drive AFTER finding line

# NEW: Ignore sensor for this many samples at start (approx 1.2 seconds)
# This prevents it from seeing the line it started on and stopping instantly.
WARMUP_SAMPLES = 40             

# Physical order on board: GREEN -> BLUE -> RED
LINE_COLORS = ("GREEN", "BLUE", "RED")

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
    Reads the current reflection, adds it to a history list,
    and returns the average.
    Returns tuple: (raw_value, smoothed_average)
    """
    raw = color_sensor.reflection()
    if raw is None: raw = 0
    
    # Pop oldest, add newest
    reflection_history.pop(0)
    reflection_history.append(raw)
    
    # Calculate average
    avg = sum(reflection_history) / len(reflection_history)
    return raw, avg


def classify_zone_from_smoothed_ref(avg_ref):
    """
    Classify based on the AVERAGE reflection value (float).
    
    Calibration Data: Red=1, Blue=2, Green=3
    Thresholds:
      RED   < 1.5
      BLUE  1.5 to 2.5
      GREEN >= 2.5
    """
    if avg_ref is None:
        return None

    if avg_ref < 1.5:
        return "RED"

    if 1.5 <= avg_ref < 2.5:
        return "BLUE"

    if avg_ref >= 2.5:
        return "GREEN"

    return None


def choose_target_color_for_scenario(s: str):
    s = s.upper()
    if s == "RECYCLING_OK":
        return "GREEN"
    if s == "CONTAMINATED":
        return "RED"
    if s in ("INSPECTION", "URGENT_INSPECTION", "URGENT_FIELD_INSPECTION"):
        return "BLUE"
    return "GREEN"


def main():
    global scenario

    print("Starting contamination sorter logic (Smoothed + Warmup)...")

    target_color = choose_target_color_for_scenario(scenario)
    print("STATUS:TARGET_COLOR=" + target_color)

    # 1. Wait a moment for sensor to stabilize
    wait(500)
    
    # 2. Pre-fill history buffer so averages aren't skewed at start
    initial_val = color_sensor.reflection()
    if initial_val is None: initial_val = 0
    for i in range(5):
        reflection_history[i] = initial_val
        
    print(f"DEBUG: Initial Sensor Read = {initial_val}")

    seen_blue = False
    seen_green = False
    seen_red = False

    consecutive_target_hits = 0
    sample_counter = 0

    hub.display.text("GO")
    drive_forward(DRIVE_SPEED)

    while True:
        sample_counter += 1

        # 1. Get RAW and SMOOTHED reflection
        raw_refl, avg_refl = get_smoothed_reflection()
        
        # 2. Map smoothed reflection to zone
        current_zone = classify_zone_from_smoothed_ref(avg_refl)
        
        dist = distance_sensor.distance()

        # --- DEBUG PRINT ---
        # Look closely at "Raw" vs "Avg". If Blue is missed, what is Raw showing?
        print(
            f"DEBUG Raw:{raw_refl} Avg:{avg_refl:.1f}",
            f"Zone:{current_zone}",
            f"Target:{target_color}",
            f"Hits:{consecutive_target_hits}"
        )

        # --- Safety: obstacle/box at either end ---
        if dist is not None and dist <= STOP_DISTANCE_MM:
            stop_motors()
            print(f"STATUS:ABORT_OBSTACLE distance_mm={dist}")
            hub.speaker.beep(400, 250)
            spin_180()
            seen_blue = seen_green = seen_red = False
            consecutive_target_hits = 0
            drive_forward(DRIVE_SPEED)
            continue

        # --- WARMUP PHASE ---
        # Ignore hits for the first ~1.2 seconds so we don't stop on the start line
        if sample_counter < WARMUP_SAMPLES:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # If detected zone is not one of our line colors, reset hit counter
        if current_zone not in LINE_COLORS:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # Mark line colors we've actually crossed
        if current_zone == "BLUE":
            seen_blue = True
        elif current_zone == "GREEN":
            seen_green = True
        elif current_zone == "RED":
            seen_red = True

        # Target hit logic
        if current_zone == target_color:
            consecutive_target_hits += 1
        else:
            consecutive_target_hits = 0

        # Stop if target reached
        if consecutive_target_hits >= CONSECUTIVE_TARGET_HITS:
            print("DEBUG: Sensor reached zone, moving rest of robot in")

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

        # --- "Wrong way" logic (GREEN -> BLUE -> RED) ---
        
        # Searching GREEN (Edge)
        if target_color == "GREEN":
            if current_zone == "BLUE":
                pass
            elif current_zone == "RED" and seen_blue and not seen_green:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_GREEN")
                spin_180()
                seen_blue = seen_green = seen_red = False
                consecutive_target_hits = 0
                drive_forward(DRIVE_SPEED)
                continue

        # Searching RED (Edge)
        if target_color == "RED":
            if current_zone == "BLUE":
                pass
            elif current_zone == "GREEN" and seen_blue and not seen_red:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_RED")
                spin_180()
                seen_blue = seen_green = seen_red = False
                consecutive_target_hits = 0
                drive_forward(DRIVE_SPEED)
                continue

        # Searching BLUE (Middle)
        if target_color == "BLUE":
            if seen_green and seen_red and consecutive_target_hits == 0:
                stop_motors()
                print("STATUS:WRONG_WAY_FOR_BLUE")
                spin_180()
                seen_blue = seen_green = seen_red = False
                consecutive_target_hits = 0
                drive_forward(DRIVE_SPEED)
                continue

        wait(SAMPLE_MS)

    hub.display.text("OK")
    print("STATUS:DONE")
    hub.speaker.beep(1500, 400)


main()