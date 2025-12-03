from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, UltrasonicSensor, ColorSensor
from pybricks.parameters import Port, Direction, Stop, Color
from pybricks.tools import wait

hub = PrimeHub()

# --- Hardware layout (based on what you confirmed works) ---

# Drive motors
left_motor = Motor(Port.C, positive_direction=Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.D, positive_direction=Direction.CLOCKWISE)

# Sensors
color_sensor = ColorSensor(Port.B)   # pointing straight down
distance_sensor = UltrasonicSensor(Port.F)   # pointing forward

# --- Tunable parameters ---

DRIVE_SPEED = 200          # deg/s for both motors when cruising forward
SAMPLE_MS = 30             # how often to sample sensors
REF_BASELINE = 60          # approximate reflection value of beige board
REF_DROP = 10              # how much darker a line must be vs baseline
CONSECUTIVE_HITS = 3       # how many consecutive dark readings count as "on a line"

# Geometry / stopping:
# You said the front arm extends ~2 inches in front of the ultrasonic sensor and
# you want the ARM to stop ~2 inches before the box.
# So sensor distance ~= 4 inches ≈ 100 mm.
STOP_DISTANCE_MM = 100     # tweak if it stops too near / too far


def drive_forward(speed):
    """Drive straight forward at given speed."""
    left_motor.run(speed)
    right_motor.run(speed)


def stop_motors():
    """Stop both motors with a brake."""
    left_motor.stop(Stop.BRAKE)
    right_motor.stop(Stop.BRAKE)


def wait_for_line(label):
    """
    Keep driving forward until the down-facing sensor sees a darker band
    than the beige background for a few consecutive samples.
    """
    print("Waiting for", label, "line...")
    hub.display.text(label[0])  # Show first letter on hub

    consecutive = 0
    while True:
        refl = color_sensor.reflection()
        col = color_sensor.color()
        print("refl:", refl, "color:", col)

        # Treat significantly darker than baseline as "on a line"
        if refl < (REF_BASELINE - REF_DROP):
            consecutive += 1
        else:
            consecutive = 0

        if consecutive >= CONSECUTIVE_HITS:
            print(label, "line reached!")
            hub.speaker.beep(800, 150)
            # small delay to make sure we've fully crossed the line
            wait(200)
            break

        wait(SAMPLE_MS)


def drive_until_box():
    """
    After the red line, keep driving forward until the ultrasonic sensor
    reads about STOP_DISTANCE_MM in front of the sensor (accounting for the
    2-inch arm ahead of the sensor).
    """
    print("Driving toward box, watching distance...")
    hub.display.text("B")

    while True:
        d = distance_sensor.distance()
        # Some firmwares return None if reading fails; guard against that
        if d is not None:
            print("distance:", d, "mm")
            if d <= STOP_DISTANCE_MM:
                print("Stopping near box (distance:", d, "mm )")
                hub.speaker.beep(1200, 250)
                break
        wait(SAMPLE_MS)


# --- Main test sequence ---

print("Starting line & distance test...")
hub.display.text("GO")
drive_forward(DRIVE_SPEED)

# 1: Blue line
wait_for_line("Blue")

# 2: Green line
wait_for_line("Green")

# 3: Red line
wait_for_line("Red")

# Then stop near the box
drive_until_box()

# Stop the robot
stop_motors()
hub.display.text("✓")
print("Test complete.")
hub.speaker.beep(1500, 400)
