from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, ColorSensor
from pybricks.parameters import Port, Color
from pybricks.messaging import BluetoothMailboxServer, TextMailbox

hub = PrimeHub()

motor_left = Motor(Port.A)
motor_right = Motor(Port.B)

server = BluetoothMailboxServer()
box = TextMailbox('cmd', server)

print("Waiting for connection...")
server.wait_for_connection()
print("Connected!")

while True:
    cmd = box.read()
    if not cmd:
        continue

    if cmd == "RECYCLE":
        motor_left.run_time(400, 1000)
        motor_right.run_time(400, 1000)
    elif cmd == "CONTAMINATED":
        motor_left.run_time(800, 1000)
        motor_right.run_time(800, 1000)
    elif cmd == "INSPECTION":
        hub.light.on(Color.RED)
        motor_left.run_time(1000, 1500)
        motor_right.run_time(1000, 1500)

    hub.light.off()
