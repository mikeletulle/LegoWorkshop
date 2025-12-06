#--- HYBRID DETECTION LOGIC EXPLANATION ---
# This script uses a two-stage approach to identify the colored zones on the board:
#
# 1. PRIMARY: Color Sensor Value (High Confidence)
#    We first check color_sensor.color(). If the internal firmware strongly identifies
#    one of our target colors (Red, Green, Yellow), we use that result for this sample.
#    (Note: We still require CONSECUTIVE_TARGET_HITS of these samples to stop the robot).
#
# 2. FALLBACK: Reflection Intensity (Low/Variable Light)
#    If the Color Sensor returns 'None' or an ambiguous value, we fall back to
#    measuring light reflection intensity.
#    - We smooth the values over time (Moving Average) to filter out noise.
#    - We compare the average against calibrated constants (CAL_RED, etc.).
#    - We only accept the match if it falls within a tight tolerance window (+/- 1.0).
#
# This hybrid approach ensures the robot works reliably even if specific lighting conditions
# cause one method to fail.

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, UltrasonicSensor, ColorSensor
from pybricks.parameters import Port, Direction, Stop, Color, Icon
from pybricks.tools import wait, StopWatch

hub = PrimeHub()

# Motors
left_motor = Motor(Port.C, positive_direction=Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.D, positive_direction=Direction.CLOCKWISE)

# Sensors
color_sensor = ColorSensor(Port.B)          # Down at board
distance_sensor = UltrasonicSensor(Port.F)  # Forward at box

# ==========================================
# --- SCENARIO CONFIGURATION ---
# ==========================================
# Options: "RECYCLING_OK", "CONTAMINATED", "INSPECTION"
# Set to CONTAMINATED to test the new Siren/Turbo features
scenario = "RECYCLING_OK"
print("STATUS:START scenario=" + scenario)

# ==========================================
# --- COLOR CALIBRATION VALUES (EDIT HERE) ---
# ==========================================
CAL_RED    = 6
CAL_GREEN  = 13
CAL_YELLOW = 16  

# NEW: How close the reading must be to count (e.g., +/- 1.0)
ZONE_TOLERANCE = 2.0

# Filter out readings that are way off
VALID_RANGE_MIN = 0
VALID_RANGE_MAX = 25 

# ==========================================
# --- TUNABLE PARAMETERS ---
# ==========================================
DRIVE_SPEED = 200               # Normal forward speed (deg/s)
TURBO_SPEED = 500               # NEW: Faster speed for Contaminated scenario
SAMPLE_MS = 30                  # Sensor sampling period (ms)
CONSECUTIVE_TARGET_HITS = 5     # Matches needed to confirm zone
VOLUME_PERCENT = 30             # Speaker volume (0-100) - Increased to 30 ensure audibility

# UPDATED: Increased to 150mm (~6 inches) to give more room to brake
STOP_DISTANCE_MM = 150          

# UPDATED: Increased to 500 degrees to drive deeper into the zone
FINAL_DRIVE_ANGLE = 250         

WARMUP_SAMPLES = 40             # Ignore sensor for first ~1.2s while driving

# Physical order on board: GREEN -> YELLOW -> RED
ZONE_COLORS = ("GREEN", "YELLOW", "RED")

# Circular buffer for smoothing reflection
reflection_history = [0, 0, 0, 0, 0]

# NEW: Timer for siren effects
effect_timer = StopWatch()
siren_last_phase = None  # Global variable to track siren state


def stop_motors():
    left_motor.stop()
    right_motor.stop()


def drive_forward(speed):
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


def get_zone_from_color(col):
    """
    Maps high-confidence color sensor readings to our zone strings.
    This acts as the PRIMARY detection method.
    """
    if col == Color.RED:
        return "RED"
    if col == Color.GREEN:
        return "GREEN"
    if col == Color.YELLOW:
        return "YELLOW"
    return None


def classify_zone_from_smoothed_ref(avg_ref):
    """
    Classifies the zone ONLY if the reading is within ZONE_TOLERANCE (+/- 1.0)
    of a calibrated value. Otherwise returns None.
    This acts as the FALLBACK detection method.
    """
    if avg_ref is None:
        return None
        
    if avg_ref < VALID_RANGE_MIN or avg_ref > VALID_RANGE_MAX:
        return None

    # Check RED (Window: 4.0 to 6.0)
    if abs(avg_ref - CAL_RED) <= ZONE_TOLERANCE:
        return "RED"
        
    # Check GREEN (Window: 10.0 to 12.0)
    if abs(avg_ref - CAL_GREEN) <= ZONE_TOLERANCE:
        return "GREEN"
        
    # Check YELLOW (Window: 12.5 to 14.5)
    if abs(avg_ref - CAL_YELLOW) <= ZONE_TOLERANCE:
        return "YELLOW"
    
    # If the value falls in the gaps (e.g. 8.0), it is not a zone.
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


def update_siren_effects():
    """
    Handles siren sounds and flashing matrix lights.
    Alternates every 400ms.
    
    Uses standard beep() which is blocking but reliable.
    We keep duration short (50ms) to minimize impact on driving smoothness.
    """
    global siren_last_phase # Access the global variable
    
    t = effect_timer.time()
    
    # Create a 800ms cycle (400ms ON, 400ms OFF)
    phase = (t % 800) < 400
    
    if siren_last_phase != phase:
        siren_last_phase = phase
        if phase:
            # Phase A: High Tone + Square Icon
            hub.display.icon(Icon.SQUARE)
            hub.speaker.beep(900, 50) # 900Hz, 50ms (Short blip)
        else:
            # Phase B: Low Tone + X Icon
            hub.display.icon(Icon.FALSE) # X shape
            hub.speaker.beep(600, 50) # 600Hz, 50ms


def main():
    global scenario

    # Set volume (30% is a good starting point for audible but not loud)
    hub.speaker.volume(VOLUME_PERCENT)

    print("Starting contamination sorter logic (Hybrid Color + Ref Window)...")
    print(f"DEBUG Config: RED={CAL_RED}, GREEN={CAL_GREEN}, YELLOW={CAL_YELLOW}, TOLERANCE={ZONE_TOLERANCE}")

    target_color = choose_target_color_for_scenario(scenario)
    print("STATUS:TARGET_COLOR=" + target_color)

    # --- NEW: DETERMINE SPEED AND MODE ---
    if scenario == "CONTAMINATED":
        target_speed = TURBO_SPEED
        hazard_mode = True
        print("ALERT: HAZARD MODE ACTIVE. TURBO SPEED ENGAGED.")
    else:
        target_speed = DRIVE_SPEED
        hazard_mode = False

    # 1. Initialize History Buffer
    wait(500)
    initial_val = color_sensor.reflection()
    if initial_val is None: initial_val = 0
    for i in range(5):
        reflection_history[i] = initial_val

    # ---------------------------------------------------------
    # NEW: PRE-CHECK (Are we already there?)
    # ---------------------------------------------------------
    # Check what zone we are sitting on RIGHT NOW (Using Hybrid Logic)
    _, initial_avg = get_smoothed_reflection()
    initial_col = color_sensor.color()
    
    # Priority 1: Color
    start_zone = get_zone_from_color(initial_col)
    # Priority 2: Reflection
    if start_zone is None:
        start_zone = classify_zone_from_smoothed_ref(initial_avg)
    
    print(f"DEBUG: Start Read={initial_val}, Start Col={initial_col}, Start Zone={start_zone}")

    if start_zone == target_color:
        print(f"DEBUG: Already on target {target_color}! Skipping drive.")
        print(f"{target_color} ZONE reached (target {target_color})")
        print(f"STATUS:{target_color}_REACHED")
        
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

    if not hazard_mode:
        hub.display.text("GO")
    else:
        effect_timer.reset() # Start siren timer

    drive_forward(target_speed)

    while True:
        sample_counter += 1

        # --- NEW: Handle Siren Effects ---
        if hazard_mode:
            update_siren_effects()

        # 1. Get Sensor Data
        # Read Color (High Priority)
        col_reading = color_sensor.color()
        # Read Reflection (Low Priority / Fallback) - Always read to keep history buffer alive
        raw_refl, avg_refl = get_smoothed_reflection()
        
        # 2. Determine Zone based on Hybrid Logic
        # Priority 1: Color Sensor Value
        current_zone = get_zone_from_color(col_reading)
        
        # Priority 2: Reflection Fallback
        if current_zone is None:
            current_zone = classify_zone_from_smoothed_ref(avg_refl)
            
        dist = distance_sensor.distance()

        # Debug print (Throttle this if it slows down the loop too much)
        # print(
        #     f"DEBUG Col:{col_reading} AvgRef:{avg_refl:.1f}",
        #     f"Zone:{current_zone}",
        #     f"Target:{target_color}",
        #     f"Hits:{consecutive_target_hits}"
        # )

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
            
            # RESUME DRIVING (With correct speed!)
            drive_forward(target_speed)
            continue

        # --- Warmup (Skip detection while moving off start ZONE) ---
        if sample_counter < WARMUP_SAMPLES:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # If detected zone is unknown, reset hits
        if current_zone not in ZONE_COLORS:
            consecutive_target_hits = 0
            wait(SAMPLE_MS)
            continue

        # Mark crossed ZONEs
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
            # Use same speed for consistency
            left_motor.run_angle(target_speed, FINAL_DRIVE_ANGLE, wait=False)
            right_motor.run_angle(target_speed, FINAL_DRIVE_ANGLE, wait=True)

            stop_motors()
            
            print(f"{current_zone} ZONE reached (target {target_color})")
            print(f"STATUS:{current_zone}_REACHED")

            if scenario.upper() == "RECYCLING_OK":
                print("STATUS:ZONE=RECYCLING_OK")
            elif scenario.upper() == "CONTAMINATED":
                print("STATUS:ZONE=CONTAMINATED")
            else:
                print("STATUS:ZONE=INSPECTION")
            break

        # --- Wrong Way Logic (GREEN -> YELLOW -> RED) ---
        # Note: We keep drive_forward(target_speed) in the resets to maintain turbo if needed
        
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
                sample_counter = 0 
                drive_forward(target_speed)
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
                drive_forward(target_speed)
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
                drive_forward(target_speed)
                continue

        wait(SAMPLE_MS)

    hub.display.text("OK")
    print("STATUS:DONE")
    hub.speaker.beep(1500, 400)


main()