"""
bridge_main.py

High-level bridge that connects:
  Salesforce Pub/Sub API  -->  LEGO SPIKE robot over BLE

Usage:

  # 1) Test just the motor/hub connection:
  python bridge_main.py --test-motor

  # 2) Full bridge: Salesforce commands -> robot motions
  python bridge_main.py

Requires:
  - spike_ble.SpikeHub
  - salesforce_pubsub.subscribe_to_commands()
  - sf_login.py has been run at least once to create sf_token_info.json
"""

import argparse
import asyncio
import logging

from spike_ble import SpikeHub
from salesforce_pubsub import subscribe_to_commands


async def run_escalation_program(hub: SpikeHub) -> None:
    """
    Visual + motion cue for 'ESCALATE' / Code Red cases.
    For now: spin motor A fast for 2 rotations.
    """
    logging.info("Running ESCALATION program on robot (fast 2 rotations)")
    await hub.run_motor_for_degrees(port="A", speed=80, degrees=720)


async def run_tier1_program(hub: SpikeHub) -> None:
    """
    Visual + motion cue for normal 'TIER_1' cases.
    For now: spin motor A slower for 1 rotation.
    """
    logging.info("Running TIER 1 program on robot (slow 1 rotation)")
    await hub.run_motor_for_degrees(port="A", speed=40, degrees=360)


async def handle_command(hub: SpikeHub, raw_command: str) -> None:
    """
    Normalize the command coming from Salesforce and dispatch to the right program.
    """
    if not raw_command:
        return

    command = raw_command.strip().upper()
    logging.info("Received command from Salesforce: %s", command)

    if command in ("ESCALATE", "CODE_RED", "HOT"):
        await run_escalation_program(hub)
    elif command in ("TIER_1", "STANDARD", "NORMAL"):
        await run_tier1_program(hub)
    else:
        logging.warning("Unknown command from Salesforce: %r", command)


async def run_bridge() -> None:
    """
    Main orchestration: connect to hub, test it, then stream commands from Salesforce.
    """
    logging.info("Starting LEGO ↔ Salesforce bridge")

    hub = SpikeHub()
    await hub.connect()

    # Quick sanity test so the audience sees the robot is "alive"
    logging.info("Performing initial motor A spin test...")
    await hub.test_spin_motor_a()

    logging.info("Now listening for Salesforce Pub/Sub commands...")
    try:
        async for command in subscribe_to_commands():
            await handle_command(hub, command)
    except asyncio.CancelledError:
        pass
    finally:
        await hub.disconnect()
        logging.info("Bridge shut down cleanly.")


async def run_motor_test_only() -> None:
    logging.info("Running motor test only (no Salesforce)...")
    hub = SpikeHub()
    await hub.connect()
    await hub.test_spin_motor_a()
    await hub.disconnect()
    logging.info("Motor test complete.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-motor",
        action="store_true",
        help="Spin motor A once to verify BLE + robot, no Salesforce involved.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        if args.test_motor:
            asyncio.run(run_motor_test_only())
        else:
            asyncio.run(run_bridge())
    except KeyboardInterrupt:
        # Friendly exit on Ctrl+C
        logging.info("KeyboardInterrupt received. Exiting bridge.")


if __name__ == "__main__":
    main()
