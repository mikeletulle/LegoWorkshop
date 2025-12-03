# WM LEGO Contamination Sorter – Setup Guide

This README explains how to set up the full environment for the **Salesforce → Pub/Sub API → Laptop Bridge → LEGO SPIKE Prime robot using Pybricks** demo.

---

## 1. Architecture Overview

```
Salesforce (Einstein Agent)
        │
        ▼
Publishes Platform Event (LEGO_Command__e)
        │
        ▼
Python Bridge on Laptop (bridge_pybricks.py)
  - Listens to Salesforce Pub/Sub API (gRPC)
  - Runs Pybricks robot program via BLE
        │
        ▼
LEGO SPIKE Prime Robot (Pybricks firmware)
  - Drives, reads sensors, prints STATUS messages
```

---

## 2. LEGO SPIKE Prime Hub Setup

### Install Pybricks Firmware

Steps:

1. Go to **https://code.pybricks.com**
2. Click the **Bluetooth icon**, select your hub, and choose **Install Pybricks firmware**.
3. If Chrome cannot detect the hub:
   - Go to `chrome://flags`
   - Enable **Experimental Web Platform Features**
   - Restart Chrome
4. If Bluetooth still doesn’t connect:
   - Use the install wizard to flash firmware over **USB**
   - **Turn off the hub**
   - Hold the **Bluetooth button**
   - While holding, plug in USB → Hub will enter DFU mode  
     → LEDs blink **pink → green → blue → off**
5. On Windows 11 you may need to install the **WinUSB** driver using the wizard.

After successful installation, the hub will reboot into Pybricks.

---

## 3. Build the Robot

Use LEGO SPIKE instructions:

### Base
- Build **Driving Base 1**  
  https://spike.legoeducation.com/prime/models/bltc58e302d70cf6530

### Attach Tools & Sensors
- Add **Tools from Driving Base 2**  
  https://spike.legoeducation.com/prime/models/blte7efff9c7c96c9cb
- Attach:
  - Left Motor → Port **C**
  - Right Motor → Port **D**
  - **ColorSensor** → Port **B** (facing downward)
  - **UltrasonicSensor** → Port **F** (facing forward)

Ensure the front bumper/arms extend ~2 inches beyond the ultrasonic sensor.

---

## 4. Laptop Environment Setup

### Install Python (recommended 3.11.x)
Check version:

```bash
python3 --version
```

### Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate    # Windows
```

### Install required Python packages

```bash
pip install grpcio grpcio-tools fastavro bleak
pip install pybricksdev
```

### Install Salesforce Pub/Sub API Python stubs

Clone the Salesforce repo:

```bash
git clone https://github.com/salesforce/pubsub-api.git
cd pubsub-api
python -m pip install .
```

This provides:

- `pubsub_api_pb2.py`
- `pubsub_api_pb2_grpc.py`

which are required by `salesforce_pubsub.py`.

---

## 5. Salesforce Authentication Setup

Run login helper:

```bash
python sf_login.py
```

This opens a browser → Salesforce login → stores token info:

```
sf_token_info.json
```

Required by the bridge.

---

## 6. Test the Salesforce Listener

```bash
python salesforce_pubsub.py
```

Publish a LEGO_Command__e event in Salesforce:

- Field: `Command__c`
- Example: `"RECYCLING_OK"`

If correct, terminal prints:

```
Received LEGO command from Salesforce: RECYCLING_OK
```

---

## 7. Test Pybricks BLE Connection

Make sure the hub is **on** and **blinking blue** (waiting for BLE).

Then run:

```bash
pybricksdev run ble my_robot_program.py
```

If working, the robot moves.

---

## 8. Run Full Integrated Bridge

```bash
python bridge_pybricks.py
```

When Salesforce publishes a command:

| Command__c          | Action |
|---------------------|--------|
| `RECYCLING_OK`      | Calm drive to “Recycling OK” zone |
| `CONTAMINATED`      | Urgent drive to “Landfill” zone |
| `INSPECTION`        | Fast drive with lights, go to “Inspection” zone |

Robot prints sensor checkpoints like:

```
STATUS: COLOR_BLUE_REACHED
STATUS: COLOR_GREEN_REACHED
STATUS: COLOR_RED_REACHED
STATUS: STOPPED_BEFORE_BOX
```

These are captured by the bridge and can be sent back to Salesforce (optional extension).

---

## 9. Troubleshooting

### BLE cannot find the hub
- Ensure Pybricks firmware is installed
- Hub must show **flashing blue light**
- Restart hub
- Try running:

```bash
pybricksdev scan
```

### Pub/Sub does not receive events
- Ensure Connected App OAuth settings allow API access
- Ensure Platform Event is set to **Publish Immediately**
- Run:

```bash
python salesforce_pubsub.py
```

to verify events arrive.

### Pybricks script fails with ENODEV
Check cables:
- Motor C (left)
- Motor D (right)
- Sensor B (ColorSensor)
- Sensor F (Ultrasonic)

---

## 10. Files in This Project

| File | Purpose |
|------|---------|
| `sf_login.py` | OAuth login → generates sf_token_info.json |
| `salesforce_pubsub.py` | Async generator that streams commands from Salesforce |
| `my_robot_program.py` | Basic test robot movement |
| `contamination_sorter.py` | Full Pybricks robot logic |
| `bridge_pybricks.py` | Glue: listens for SF commands → runs Pybricks program |
| `README.md` | This guide |

---

## 11. Credits

Built for the **Waste Management LEGO Challenge Workshop** using:

- Salesforce Einstein Agentforce
- Salesforce Pub/Sub API (gRPC)
- Pybricks firmware for LEGO SPIKE Prime
- Python robotics bridge

