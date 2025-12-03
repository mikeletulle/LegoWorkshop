# bridge_pybricks.py
#
# High-level bridge that connects:
#   Salesforce Pub/Sub (LEGO_Command__e.Command__c)
#   --> Pybricks program on the SPIKE Prime hub (contamination_sorter.py)
#
# For each incoming command like "RECYCLING_OK", "CONTAMINATED", or
# "INSPECTION", this script:
#   1) Maps it to a scenario string for the Pybricks program.
#   2) Creates a temporary copy of contamination_sorter.py with
#      `scenario = "<SCENARIO>"` baked in.
#   3) Runs: pybricksdev run ble <that-temp-script>
#   4) Streams stdout/stderr from Pybricks, looking for lines starting with
#      "STATUS:" that describe robot progress.

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional

# Updated imports to include publish_robot_status
from salesforce_pubsub import subscribe_to_commands, publish_robot_status

log = logging.getLogger(__name__)

# Path to the base Pybricks script (the "template")
CONTAMINATION_TEMPLATE = Path("contamination_sorter.py")

# Base pybricksdev command (no extra args here)
PYBRICKS_CMD_PREFIX = ["pybricksdev", "run", "ble"]


async def run_contamination_sorter(scenario: str) -> List[str]:
    """
    Launches the Pybricks contamination_sorter.py program over BLE with the
    given scenario.

    Instead of passing the scenario as a CLI arg (which pybricksdev does not
    support), we:
      1) Read contamination_sorter.py
      2) Replace the `scenario = "..."` line with the chosen scenario
      3) Write a temporary script file
      4) Run pybricksdev on that temporary script
    """
    scenario = scenario.upper()

    # 1) Load the template script
    try:
        src = CONTAMINATION_TEMPLATE.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.error(
            "Base Pybricks script %s not found. "
            "Make sure contamination_sorter.py is in the same folder "
            "as bridge_pybricks.py.",
            CONTAMINATION_TEMPLATE,
        )
        return []

    # 2) Replace the scenario line
    #
    # We assume there is a line near the top like:
    #   scenario = "RECYCLING_OK"
    #
    # This replacement is safe to run every time before sending to the hub.
    new_src, n_subs = re.subn(
        r'^scenario\s*=\s*".*"$',
        f'scenario = "{scenario}"',
        src,
        count=1,
        flags=re.MULTILINE,
    )
    if n_subs == 0:
        log.warning(
            "Did not find a `scenario = \"...\"` line to replace in %s. "
            "The script will still use whatever default is defined.",
            CONTAMINATION_TEMPLATE,
        )
        new_src = src  # fall back to original

    # 3) Write a temporary script file (one per scenario so logs are clearer)
    tmp_script = Path(f"contamination_sorter_runtime_{scenario}.py")
    tmp_script.write_text(new_src, encoding="utf-8")

    cmd = PYBRICKS_CMD_PREFIX + [str(tmp_script)]
    log.info("Starting Pybricks program: %s", " ".join(cmd))

    # IMPORTANT: use stdout/stderr=PIPE, and decode bytes manually.
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    status_lines: List[str] = []

    async def _read_stream(stream, prefix: str):
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="ignore").rstrip()
            log.info("[%s] %s", prefix, text)
            if text.startswith("STATUS:"):
                status_lines.append(text)

    # Read both stdout and stderr concurrently
    await asyncio.gather(
        _read_stream(proc.stdout, "pybricks stdout"),
        _read_stream(proc.stderr, "pybricks stderr"),
    )

    rc = await proc.wait()
    log.info("Pybricks process exited with return code %s", rc)

    if not status_lines:
        log.info("No STATUS lines were returned by contamination_sorter.py.")

    return status_lines


def _map_command_to_scenario(raw_command: Optional[str]) -> Optional[str]:
    """
    Normalize and map the Salesforce Command__c value to one of the
    contamination_sorter scenarios.
    """
    if not raw_command:
        return None

    cmd = raw_command.strip().upper()
    log.info("Received command from Salesforce: %s", cmd)

    if cmd in ("RECYCLING_OK", "OK", "NORMAL"):
        log.info("Interpreted as RECYCLING_OK scenario.")
        return "RECYCLING_OK"

    if cmd in ("CONTAMINATED", "LANDFILL", "ROUTE_TO_LANDFILL"):
        log.info("Interpreted as CONTAMINATED scenario.")
        return "CONTAMINATED"

    if cmd in (
        "URGENT_FIELD_INSPECTION",
        "URGENT_INSPECTION",
        "INSPECTION",
        "FIELD_INSPECTION",
    ):
        log.info("Interpreted as INSPECTION scenario.")
        return "INSPECTION"

    log.warning("Unknown Salesforce command: %r – ignoring.", cmd)
    return None


async def handle_command(raw_command: str, case_id: Optional[str] = None) -> None:
    """
    Map the Salesforce command to a scenario, run the Pybricks program,
    and log STATUS lines.
    
    If the robot reports that it reached a zone, we publish the result back 
    to Salesforce with the Case ID.
    """
    scenario = _map_command_to_scenario(raw_command)
    if scenario is None:
        return

    try:
        status_lines = await run_contamination_sorter(scenario)
        
        # Check robot output for specific completion markers
        # The robot prints e.g., "STATUS:GREEN_REACHED" or "STATUS:RED_REACHED"
        target_reached = False
        final_zone_reported = "UNKNOWN"

        for line in status_lines:
            log.info("Robot STATUS: %s", line)
            if "_REACHED" in line:
                target_reached = True
                # Extract zone if needed, e.g. STATUS:GREEN_REACHED -> GREEN
                # but specifically we want to send the exact message requested.
                parts = line.split(":")
                if len(parts) > 1:
                    final_zone_reported = parts[1]

        if target_reached:
            log.info("Target zone reached! Publishing event back to Salesforce...")
            
            # Prepare fields for the response event
            extra = {}
            if case_id:
                extra["Case_Id__c"] = case_id
            
            # We use asyncio.to_thread because publish_robot_status uses 'requests' (synchronous)
            await asyncio.to_thread(
                publish_robot_status,
                command=raw_command,
                phase="COMPLETED",
                message="Target Zone Reached",
                board_position=final_zone_reported,
                extra_fields=extra
            )

    except Exception:
        log.exception("Error while running contamination sorter for scenario %s", scenario)


async def run_bridge() -> None:
    """
    Main orchestration: subscribe to Salesforce Pub/Sub and dispatch to Pybricks.
    """
    log.info("Starting Salesforce ↔ Pybricks contamination sorter bridge")

    try:
        # subscribe_to_commands now yields a dict containing command and case_id
        async for data in subscribe_to_commands():
            cmd = data.get("command")
            case_id = data.get("case_id")
            if cmd:
                await handle_command(cmd, case_id)

    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("Unexpected error in bridge loop.")
    finally:
        log.info("Bridge loop ended.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(run_bridge())
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received. Exiting bridge.")


if __name__ == "__main__":
    main()