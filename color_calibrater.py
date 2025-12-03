from pybricks.hubs import PrimeHub
from pybricks.pupdevices import ColorSensor
from pybricks.parameters import Port
from pybricks.tools import wait

hub = PrimeHub()
cs = ColorSensor(Port.B)

print("Starting color calibration...")
hub.display.text("C")  # Just show 'C' for Calibration

# Let this run until you stop the program from the UI
while True:
    refl = cs.reflection()
    amb = cs.ambient()
    col = cs.color()

    print("REF =", refl, "  AMB =", amb, "  COLOR =", col)

    wait(200)
