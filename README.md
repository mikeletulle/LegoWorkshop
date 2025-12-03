# LEGO Contamination Sorter – Salesforce + Pybricks Bridge

This project connects a LEGO SPIKE Prime robot running Pybricks to Salesforce using the Pub/Sub API.  
It listens for **LEGO_Command__e** platform events and drives the robot to the correct zone (Recycling OK, Contaminated, Inspection).  
After reaching the zone, it publishes back a **LEGO_Robot_Status__e** event.

---

## Board Layout

![Robot board](robot_board.png)

---

## Sensor Placement

The downward-facing Color Sensor is positioned like this:

![Sensor Placement](sensor_placement.png)

---

## How It Works – Architecture Overview

1. **Salesforce**
   - Agent or automation publishes a *LEGO_Command__e* event:
     - `Command__c` = `RECYCLING_OK`, `CONTAMINATED`, or `INSPECTION`
     - `Case_Id__c` = the originating Case Id
   - The robot returns a *LEGO_Robot_Status__e* event:
     - `Case_Id__c`
     - `Message__c` (e.g., “Target Zone Reached”)

2. **Python Bridge (`bridge_pybricks.py`)**
   - Subscribes to Salesforce Pub/Sub
   - When a command arrives:
     - Runs `pybricksdev run ble contamination_sorter.py`
     - Parses `STATUS:` output
     - Publishes a Robot Status PE back to Salesforce

3. **Pybricks Program (`contamination_sorter.py`)**
   - Uses **reflection values**, not color names
   - Detects RED / BLUE / GREEN zones
   - Drives to appropriate location
   - Sends status lines back to the Python bridge

---

## Color Detection (Reflection-Based)

The Color Sensor `.color()` readings are unreliable for this board, so `.reflection()` is used.

Use **color_calibrater.py** to measure reflection values on each zone.

### Example classifier

```python
def classify_zone_from_reflection(ref_val):
    if ref_val is None:
        return None

    if ref_val == 1:
        return "RED"
    if ref_val == 2:
        return "BLUE"
    if ref_val >= 3:
        return "GREEN"

    return None
```

---

## Salesforce Setup

### 1. Connected App (External Client App)

Name: **Lego Agent Bridge**  
Callback URL: `http://localhost:8080/callback`

Scopes:
- Manage user data via APIs (`api`)
- Full access (`full`)
- Refresh tokens (`refresh_token`, `offline_access`)
- Access the Salesforce API Platform (`sfap_api`)

Create file:

```json
// sf_config.json
{
  "CLIENT_ID": "xxxx",
  "CLIENT_SECRET": "xxxx"
}
```

---

### 2. Platform Events

#### **LEGO_Command__e**
| Field | Purpose |
|-------|---------|
| `Command__c` | `RECYCLING_OK`, `CONTAMINATED`, `INSPECTION` |
| `Case_Id__c` | originating Case ID |

#### **LEGO_Robot_Status__e**
| Field | Purpose |
|-------|---------|
| `Case_Id__c` | echoed ID |
| `Message__c` | e.g., “Target Zone Reached” |

---

### Test with Anonymous Apex

```apex
LEGO_Command__e eventRecord = new LEGO_Command__e(
    Command__c = 'INSPECTION',
    Case_Id__c = '500KZ00000F7XmZYAV'
);
Database.SaveResult sr = EventBus.publish(eventRecord);
System.debug('SR: ' + sr);
```

---

## Pybricks Firmware Installation

Steps:

- Go to https://code.pybricks.com
- Click the **Bluetooth icon**, select your hub, and install
- If Bluetooth scanning doesn’t work:
  - Go to `chrome://flags`
  - Enable **Experimental Web Platform Features**
- If Bluetooth still fails:
  - Hold hub Bluetooth button
  - Plug USB cable into laptop (flashing **pink → green → blue**)
- On Windows 11, you might need the **WinUSB** driver via Pybricks troubleshooting wizard

---

## Laptop Setup

### Create environment & install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Required packages

- pybricksdev  
- grpcio  
- fastavro  
- aiohttp  
- requests  

---

## Running the System

Start bridge:

```bash
python bridge_pybricks.py
```

Send command via Salesforce Debug Anonymous (Apex).

---

## Project Files

- `bridge_pybricks.py`
- `salesforce_pubsub.py`
- `contamination_sorter.py`
- `color_calibrater.py`
- `sf_login.py`
- `sf_config.json` (local only)
- `robot_board.png`
- `sensor_placement.png`

---

## Troubleshooting

- If robot doesn’t move: test with  
  `pybricksdev run ble contamination_sorter.py`
- If STATUS lines don’t appear: ensure contamination_sorter.py prints `STATUS:...`
- BLE errors: reboot hub & re-enable Chrome flags

