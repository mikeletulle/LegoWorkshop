# LEGO Contamination Sorter – Salesforce + Pybricks + SPIKE Prime

Repo: https://github.com/mikeletulle/LegoWorkshop

This project connects Salesforce Agentforce (or Flows/other automation) to a LEGO SPIKE Prime robot running Pybricks. The robot acts as a **“Contamination Sorter”** that drives to different zones on a board based on a Salesforce decision, and then reports its status back to Salesforce.

---

## 1. Concept – Contamination Sorter

### Table Zones

- **Recycling OK**
- **Contaminated – Route to Landfill**
- **Urgent Field Inspection**

### Scenario

1. An incoming case / inspection report describes what was found in a bin or truck:  
   - “Bag full of batteries”  
   - “Food waste in recycling”  
   - “Normal mixed paper and plastic”  
2. A Salesforce Agent / Flow / Apex decides how serious the contamination is and publishes a **`LEGO_Command__e`** platform event with:
   - **`Command__c`** – `"RECYCLING_OK"`, `"CONTAMINATED"`, or `"INSPECTION"`  
   - **`Case_Id__c`** – Id of the related Case

### Robot Behavior

- **“Recycling OK”** → Drives in a calm, normal speed to the **Recycling OK** zone.
- **“Contaminated”** → Drives fast with “hazard mode” siren to the **Contaminated / Landfill** zone.
- **“Urgent Field Inspection”** → Drives to the **Urgent Inspection** zone with distinctive behavior.

When the robot reaches the target zone, it publishes a **`LEGO_Robot_Status__e`** event back into Salesforce so the Agent / Flow can log “Target Zone Reached” on the Case.

---

## 2. High-Level Architecture

```text
Salesforce (Agent / Flow / Apex)
        |
        | 1) Publishes LEGO_Command__e
        v
Laptop Bridge (Python, Pub/Sub API)
        - sf_login.py      (OAuth 2.0 login, saves sf_token_info.json)
        - salesforce_pubsub.py (Pub/Sub gRPC client, status publisher)
        - bridge_pybricks.py   (command → robot scenario runner)
        |
        | 2) Runs `pybricksdev run ble contamination_sorter.py`
        v
LEGO SPIKE Prime Hub (Pybricks)
        - contamination_sorter.py (drives to zones, prints STATUS lines)
        |
        | 3) STATUS:XXX lines over BLE console
        |
        v
Laptop Bridge
        |
        | 4) Publishes LEGO_Robot_Status__e
        v
Salesforce
        - Updates Case / Timeline / Screen with “Robot reached target zone”
```

Key points:

- **Pub/Sub gRPC** is used to subscribe to `LEGO_Command__e` from Salesforce.
- The bridge uses **Pybricks + pybricksdev** to send `contamination_sorter.py` over BLE to the hub.
- The Pybricks program prints **`STATUS:`** lines; the bridge parses those and sends a **`LEGO_Robot_Status__e`** event back with:
  - `Command__c`
  - `Phase__c` (e.g., `"COMPLETED"`)
  - `Message__c` (e.g., `"Target Zone Reached"`)
  - `Board_Position__c` (e.g., `"GREEN_REACHED"`)
  - `Case_Id__c` (from the original command event)

---

## 3. Build the LEGO Robot

We use LEGO’s official drive bases for reliable motor and sensor placement.

### 3.1 Start with Driving Base 1

Model: **Driving Base 1**  
https://spike.legoeducation.com/prime/models/bltc58e302d70cf6530

This gives:

- Dual-motor drive
- Stable chassis
- Correct motor alignment

### 3.2 Add Distance Sensor from “Driving Base 2 – Tools & Accessories”

Model: **Tools and Accessories from Driving Base 2**  
https://spike.legoeducation.com/prime/models/blte7efff9c7c96c9cb

This adds:

- Sensor mounts
- Front extension arm
- More stable structure

### 3.3 Add Sensors

We use:

| Sensor Type       | Port | Notes                                                                 |
|-------------------|------|-----------------------------------------------------------------------|
| **Color Sensor**  | B    | Mounted downward on the front to detect board colors (zones).        |
| **Ultrasonic**    | F    | Mounted facing forward to stop before hitting the “box” (obstacle).  |

### 3.4 Board Layout & Sensor Placement

In the repo, you’ll find two reference photos:

- `robot_board.png` – Example of the board layout with **Blue → Green → Red** lines and a box at the far end.  
  ![Board Setup](robot_board.png)

- `sensor_placement.png` – Where the color sensor is mounted, pointing straight down near the front.  
  ![Sensor Placement](sensor_placement.png)

---

## 4. Flash / Install Pybricks Firmware on the Hub

You only need to do this once per hub. After that, you can just use `pybricksdev` to run programs.
Note this has already been done for hubs at workshop

1. Open **Pybricks** in Chrome or Edge:  
   🔗 https://code.pybricks.com

2. Make sure **Bluetooth is ON** on your computer and the SPIKE hub.

3. Click the **Bluetooth icon** in the top bar of the Pybricks site.
   - Select your hub and follow the prompts.
   - The site will offer to install Pybricks firmware if it isn’t already installed.

4. If Bluetooth scan doesn’t find the hub:
   - In Chrome, go to `chrome://flags` and enable  
     **“Experimental Web Platform Features”**, then restart Chrome.
   - If it *still* doesn’t work, use the USB wizard:
     - Turn hub OFF.
     - **Hold down the Bluetooth button** on the hub.
     - While holding, plug in the USB cable to laptop.
     - The hub should go into DFU/bootloader mode (pink → green → blue → off flash sequence).
     - Follow the Pybricks wizard to install firmware.

5. **Windows note (USB driver):**  
   On Windows 11, you may need to let the Pybricks troubleshooting wizard install a **WinUSB** driver for the hub before firmware installation works reliably.

6. Once installed, you should be able to connect from the Pybricks web IDE and run simple test programs.

> For the workshop, hubs will already have Pybricks firmware installed, so participants can skip straight to using `pybricksdev run ble ...`.

---

## 5. Laptop Setup (Mac & Windows)

These steps assume a **clean laptop** with no preinstalled Python tools. They work for both macOS and Windows.

### 5.1 Install Python

1. Go to:  
   🔗 https://www.python.org/downloads/

2. Download **Python 3.12+** for your OS. (*64-bit version)

3. **Windows:**  
   - Run the installer.
   - Make sure you check **“Add Python to PATH”** on the first screen.
   - Complete installation.

4. **macOS:**  
   - Run the `.pkg` installer and follow the prompts.
   - After install, open **Terminal** and confirm:

   ```bash
   python --version
   python -m pip --version
   ```

5. **Windows BLE note:**  
   If `pybricksdev` later has trouble finding your hub over BLE:
   - Confirm you installed **64-bit** Python (not ARM).
   - Restart Windows after installing Python.
   - Use a supported Bluetooth adapter and follow Pybricks’ own troubleshooting if needed.

### 5.2 Clone the LegoWorkshop Repo

```bash
# Pick any folder you like
cd ~

# Clone the project (or download it and unzip)
git clone https://github.com/mikeletulle/LegoWorkshop.git

cd LegoWorkshop
```

You should now see:

```text
README.md
bridge_main.py
bridge_pybricks.py
color_calibrater.py
contamination_sorter.py
pubsub_api.proto
pubsub_api_pb2.py
pubsub_api_pb2_grpc.py
requirements.txt
robot_board.png
salesforce_pubsub.py
sensor_placement.png
sf_login.py
```

### 5.3 Create and Activate a Virtual Environment

**macOS / Linux:**

```bash
cd LegoWorkshop

# Create venv
python -m venv venv

# Activate
source venv/bin/activate
```

**Windows (PowerShell or Command Prompt):**

```bash
cd LegoWorkshop

# Create venv
python -m venv venv

# Activate
venv\Scriptsctivate
```

You should see `(venv)` at the beginning of your shell prompt.

### 5.4 Install Python Dependencies

With the virtual environment active (`(venv)` visible), run:

```bash
pip install -r requirements.txt
```

This will install everything needed, including:

- `grpcio`, `grpcio-tools` – Salesforce Pub/Sub gRPC client
- `fastavro` (if present) / Avro support – decoding Pub/Sub event payloads
- `requests` – REST calls back to Salesforce
- `pybricksdev` – sending Pybricks programs to the SPIKE hub over BLE

> If you get `ModuleNotFoundError: No module named 'pybricksdev'`, install it explicitly:

```bash
pip install pybricksdev
```

---

## 6. Salesforce Setup

### 6.1 External Client App (OAuth 2.0)

Create an **External Client App** in Setup:

- **Name:** `Lego Agent Bridge`
- **Callback URL:**  
  `http://localhost:8080/callback`
- **OAuth scopes:**
  - `Manage user data via APIs (api)`
  - `Full access (full)`
  - `Perform requests at any time (refresh_token, offline_access)`
  - `Access the Salesforce API Platform (sfap_api)`

Record the **Client Id** and **Client Secret** – you’ll need them for `sf_config.json`.

### 6.2 Platform Events

#### 6.2.1 Command Event – LEGO_Command__e

Create a Platform Event: **`LEGO_Command__e`**

Fields (at minimum):

- `Command__c` (Text) – values like `"RECYCLING_OK"`, `"CONTAMINATED"`, `"INSPECTION"`
- `Case_Id__c` (Text or Lookup to Case) – the Case Id that triggered the robot run

Your Agent / Flow / Apex logic should publish this event when you want the robot to move.

#### 6.2.2 Status Event – LEGO_Robot_Status__e

Create a Platform Event: **`LEGO_Robot_Status__e`**

Suggested fields:

- `Command__c` (Text) – the command that was executed
- `Phase__c` (Text) – e.g. `"COMPLETED"`, `"ERROR"`, `"IN_PROGRESS"`
- `Message__c` (Long Text) – human-readable status like `"Target Zone Reached"`
- `Board_Position__c` (Text) – e.g. `"GREEN_REACHED"`, `"RED_REACHED"`
- `Case_Id__c` (Text or Lookup to Case) – so you can tie the status back to the originating Case

The bridge code calls `publish_robot_status(...)` in `salesforce_pubsub.py` to create these events.

---

## 7. Local Salesforce OAuth Setup

In the **LegoWorkshop** folder, create a file called `sf_config.json`:

```json
{
  "CLIENT_ID": "YOUR_CONNECTED_APP_CLIENT_ID",
  "CLIENT_SECRET": "YOUR_CONNECTED_APP_CLIENT_SECRET"
}
```

Make sure this file is **in the same folder** as `sf_login.py`.

### 7.1 Run sf_login.py

With your virtual environment active in `LegoWorkshop`:

```bash
python sf_login.py
```

What this does:

1. Opens Salesforce login in your browser.
2. You log in and authorize the app.
3. Salesforce redirects back to `http://localhost:8080/callback`.
4. `sf_login.py` exchanges the code for a token and saves **`sf_token_info.json`**.

You should see a success message like:

> SUCCESS! Saved Salesforce token info to: sf_token_info.json  
> This is what salesforce_pubsub.py will read automatically.

You only need to rerun this when your refresh token is invalid or you change org / client app.

---

## 8. Color Calibration & Detection

### 8.1 Color Calibration (color_calibrater.py)

Because the Color Sensor readings vary with ambient light and sensor height, the project uses a hybrid detection strategy in contamination_sorter.py:

1. Wake up the hub and enable Bluetooth.
2. With the venv active, run:

```bash
pybricksdev run ble color_calibrater.py
```

3. Slowly move the robot over each colored stripe (Green, Yellow, Red) on your board.
4. Watch the printed reflection values and note the typical averages:
   - Example:  
     - Red ~ 7  
     - Green ~ 13  
     - Yellow ~ 16

5. Open `contamination_sorter.py` and adjust:

```python
CAL_RED    = 7
CAL_GREEN  = 13
CAL_YELLOW = 16
ZONE_TOLERANCE = 2.0
```

These constants are used by:

```python
def classify_zone_from_smoothed_ref(avg_ref):
    ...
```

### 8.2 Robot Behavior Script (contamination_sorter.py)

Key features:

If it strongly identifies Color.RED, Color.GREEN, or Color.YELLOW, that is used as the zone.
Multiple consecutive hits are required before accepting.
Fallback: color_sensor.reflection()
A moving average is computed over recent readings.
The average is compared against calibrated constants.
Only treated as a zone if the average is within a small tolerance window.

- Uses **motors on C and D** to drive straight.
- Uses **ColorSensor on B** to detect colored zones.
- Uses **UltrasonicSensor on F** to stop before hitting the box.
- Implements **hybrid detection**:
  - Primary: `color_sensor.color()` (RED, GREEN, YELLOW).
  - Fallback: reflection averages and calibrated thresholds.
- Uses **scenario** variable near the top:

```python
scenario = "RECYCLING_OK"  # or "CONTAMINATED" or "INSPECTION"
```

The bridge (`bridge_pybricks.py`) automatically rewrites this line for each scenario it runs.

It prints `STATUS:` lines such as:

- `STATUS:TARGET_COLOR=GREEN`
- `STATUS:GREEN_REACHED`
- `STATUS:ZONE=RECYCLING_OK`
- `STATUS:DONE`
- `STATUS:WRONG_WAY_FOR_RED`
- `STATUS:ABORT_OBSTACLE distance_mm=...`

The bridge parses those to decide when to send a status event back to Salesforce.

---

## 9. Running the Full Bridge

### 9.1 Make Sure the Hub is Ready

- Pybricks firmware is installed (see earlier steps).
- The hub is **powered on** and in normal mode (not DFU).
- Bluetooth is enabled on the hub (press the Bluetooth button until it shows the Bluetooth icon / blue LED).

### 9.2 Start the Bridge

With the venv active in the `LegoWorkshop` folder:

```bash
python bridge_pybricks.py
```

You should see logs such as:

```text
[INFO] salesforce_pubsub: Loaded Salesforce auth metadata from sf_token_info.json
[INFO] salesforce_pubsub: Pub/Sub subscription thread started...
[INFO] salesforce_pubsub: Fetched Avro schema ... for topic /event/LEGO_Command__e
[INFO] salesforce_pubsub: Subscribing to /event/LEGO_Command__e on api.pubsub.salesforce.com:7443
```

The script now waits for `LEGO_Command__e` events.

### 9.3 Quick End-to-End Test from Salesforce

1. Open **Developer Console** in Salesforce.
2. Open **Execute Anonymous** (Debug → Open Execute Anonymous Window).
3. Paste and run:

```apex
LEGO_Command__e eventRecord = new LEGO_Command__e(
    Command__c = 'INSPECTION',
    Case_Id__c = '500KZ00000F7XmZYAV' // replace with a real Case Id in your org
);
Database.SaveResult sr = EventBus.publish(eventRecord);
System.debug('SR: ' + sr);
```

4. In your terminal running `bridge_pybricks.py`, you should see:

   - The decoded `LEGO_Command__e` record.
   - `Received LEGO command: INSPECTION (Case: 500...)`
   - `Interpreted as INSPECTION scenario.`
   - Pybricks logs as it drives across the board and hits the yellow zone.
   - One or more `STATUS:` lines like `STATUS:YELLOW_REACHED` and `STATUS:DONE`.

5. After `STATUS` lines are seen, the bridge will publish a **`LEGO_Robot_Status__e`** event back to Salesforce with:
   - `Command__c = 'INSPECTION'`
   - `Phase__c = 'COMPLETED'`
   - `Message__c = 'Target Zone Reached'`
   - `Board_Position__c = 'YELLOW_REACHED'` (example)
   - `Case_Id__c = '500KZ00000F7XmZYAV'`

You can then:

- Subscribe to `LEGO_Robot_Status__e` in **Event Monitoring**, or  
- Use a **Flow / Trigger** to update the Case with the latest robot status.

---

## 10. Tips & Troubleshooting

- **Hub not found via BLE (pybricksdev):**
  - Make sure the hub is on and Bluetooth is enabled.
  - Make sure no other app (official SPIKE app, Pybricks web IDE) is connected.
  - On Windows, verify you installed 64-bit Python, restart, and try again.
  - Run a quick test:
    ```bash
    pybricksdev run ble my_robot_program.py
    ```

- **No commands arriving in bridge_pybricks logs:**
  - Verify `sf_token_info.json` exists and was created by `sf_login.py` in the same folder.
  - Check Connected App scopes include `sfap_api` and `api`.
  - Confirm the **Topic Name** in `salesforce_pubsub.py` matches your event name (`/event/LEGO_Command__e`).

- **Status events not appearing:**
  - Ensure **`LEGO_Robot_Status__e`** and its fields exactly match the names used in `publish_robot_status()` (especially `Message__c` and `Case_Id__c`).
  - Check debug logs for warnings like “Failed to publish LEGO_Robot_Status__e”.

---

You now have a complete Salesforce → Pub/Sub → Python → Pybricks → LEGO robot → Salesforce loop.

This setup is intentionally simple and hackathon-friendly: everything is plain Python scripts, a single repo, and standard platform events. Once it’s working, you can easily extend it with richer robot behaviors, more complex Agent prompts, or additional telemetry.
