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
scenario = "CONTAMINATED"
print("STATUS:START scenario=" + scenario)

# --- Tunable parameters ---

DRIVE_SPEED = 200               # forward speed (deg/s)
SAMPLE_MS = 30                  # sensor sampling period (ms)
CONSECUTIVE_TARGET_HITS = 5     # how many consecutive "target color" samples to stop
STOP_DISTANCE_MM = 100          # distance to stop before box
FINAL_DRIVE_ANGLE = 360         # Degrees to drive AFTER finding line (360 ~= 1 wheel rotation ~= 7 inches)

# Physical order on board: GREEN -> BLUE -> RED
LINE_COLORS = ("GREEN", "BLUE", "RED")


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


def classify_zone_from_reflection(ref_val):
    """
    Classify board zone purely from reflection.
    Returns "GREEN", "BLUE", "RED", or None.
    """
    if ref_val is None:
        return None

    # RED: darkest
    if ref_val == 1:
        return "RED"

    # BLUE: medium
    if ref_val == 2:
        return "BLUE"

    # GREEN: brighter
    if ref_val >= 3:
        return "GREEN"

    # Fallback
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

    print("Starting contamination sorter logic (Reflection Only)...")

    target_color = choose_target_color_for_scenario(scenario)
    print("STATUS:TARGET_COLOR=" + target_color)

    # Track which lines we've actually crossed
    seen_blue = False
    seen_green = False
    seen_red = False

    consecutive_target_hits = 0
    sample_counter = 0

    hub.display.text("GO")
    drive_forward(DRIVE_SPEED)

    while True:
        sample_counter += 1

        # 1. Get raw reflection ONLY
        refl = color_sensor.reflection()
        dist = distance_sensor.distance()

        # 2. Map reflection to a zone string
        current_zone = classify_zone_from_reflection(refl)

        # --- DEBUG PRINT EVERY TIME ---
        print(
            "DEBUG Refl:", refl,
            "Zone:", current_zone,
            "Target:", target_color
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

        # If detected zone is not one of our line colors (None), reset hit counter
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
            # 1. Announce we found it
            print("DEBUG: Sensor reached zone, moving rest of robot in")

            # 2. Drive the extra distance (blocking until done)
            # We run one motor with wait=False and the other wait=True to run them together
            left_motor.run_angle(DRIVE_SPEED, FINAL_DRIVE_ANGLE, wait=False)
            right_motor.run_angle(DRIVE_SPEED, FINAL_DRIVE_ANGLE, wait=True)

            # 3. NOW we stop
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