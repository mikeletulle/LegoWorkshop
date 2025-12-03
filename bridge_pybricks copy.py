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

from salesforce_pubsub import subscribe_to_commands

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


async def handle_command(raw_command: str) -> None:
    """
    Map the Salesforce command to a scenario, run the Pybricks program,
    and log STATUS lines. (Later we can push STATUS back to Salesforce.)
    """
    scenario = _map_command_to_scenario(raw_command)
    if scenario is None:
        return

    try:
        status_lines = await run_contamination_sorter(scenario)
        # For now, just log the STATUS lines; later we can create a Case
        # update or platform event back to Salesforce with these.
        for line in status_lines:
            log.info("Robot STATUS: %s", line)
    except Exception:
        log.exception("Error while running contamination sorter for scenario %s", scenario)


async def run_bridge() -> None:
    """
    Main orchestration: subscribe to Salesforce Pub/Sub and dispatch to Pybricks.
    """
    log.info("Starting Salesforce ↔ Pybricks contamination sorter bridge")

    try:
        async for cmd in subscribe_to_commands():
            await handle_command(cmd)
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
