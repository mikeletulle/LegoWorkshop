from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, UltrasonicSensor, ColorSensor
from pybricks.parameters import Port, Direction, Color
from pybricks.tools import wait

hub = PrimeHub()

# --- Motors: you said this combo drives straight, so we keep it ---
left_motor = Motor(Port.C, positive_direction=Direction.COUNTERCLOCKWISE)
right_motor = Motor(Port.D, positive_direction=Direction.CLOCKWISE)

# --- Sensors with safe init so ENODEV doesn't crash the program ---

ultra = None
color = None

try:
    ultra = UltrasonicSensor(Port.F)
except OSError:
    # No ultrasonic on F
    hub.display.text("No US F")
    wait(1000)

try:
    color = ColorSensor(Port.B)
except OSError:
    # No color sensor on B
    hub.display.text("No Col B")
    wait(1000)

# --- Helper functions ---

def drive_straight(speed=300):
    left_motor.run(speed)
    right_motor.run(speed)

def stop():
    left_motor.stop()
    right_motor.stop()

# --- Main behavior: drive forward, use sensors if available ---

hub.light.on(Color.GREEN)
drive_straight(300)

while True:
    # If we have ultrasonic sensor, use it to stop when close to something
    if ultra is not None:
        d = ultra.distance()  # distance in mm, or None
        if d is not None and d < 200:
            stop()
            hub.light.on(Color.RED)
            hub.display.text("STOP")
            break

    # If we have color sensor, you can watch values in terminal
    if color is not None:
        # This will print a Color enum (RED, BLUE, etc.)
        c = color.color()
        print("Color:", c)

    wait(50)

# Keep program alive so you can see the STOP state
while True:
    wait(1000)
