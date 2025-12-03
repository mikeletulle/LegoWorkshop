"""
spike_ble.py

Low-level BLE interface to a LEGO SPIKE Prime (or similar) hub using the
LEGO Wireless Protocol 3.0 over Bluetooth LE.

This version:
- Uses BleakScanner.discover(return_adv=True) to also get advertisement data.
- Matches the hub by the LEGO Wireless Protocol 3.0 service UUID, so it works
  even if the device name is "None" or something unexpected.

Public async API:
  - connect()
  - disconnect()
  - run_motor_for_degrees(port="A", speed=50, degrees=360)
  - test_spin_motor_a()
"""

import asyncio
import logging
from typing import Optional

from bleak import BleakScanner, BleakClient

# Port IDs for external ports A–F (0x00..0x05)
PORT_NAME_TO_ID = {
    "A": 0x00,
    "B": 0x01,
    "C": 0x02,
    "D": 0x03,
    "E": 0x04,
    "F": 0x05,
}

# LEGO Wireless Protocol 3.0 GATT UUIDs
LEGO_HUB_SERVICE_UUID = "00001623-1212-efde-1623-785feabcd123"
LEGO_HUB_CHAR_UUID = "00001624-1212-efde-1623-785feabcd123"

log = logging.getLogger(__name__)


class SpikeHub:
    """
    Thin helper for talking to a SPIKE hub via BLE using bleak.

    Public async API:
      - connect()
      - disconnect()
      - run_motor_for_degrees()
      - test_spin_motor_a()
    """

    def __init__(self, device_name_hint: Optional[str] = None) -> None:
        """
        :param device_name_hint: Optional substring to match hub name (e.g. 'SPIKE').
                                 Used as a tiebreaker if multiple LEGO hubs are found.
        """
        self._device_name_hint = device_name_hint
        self._client: Optional[BleakClient] = None

    # ------------------------------------------------------------------ #
    # Connection management                                              #
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """
        Scan for a SPIKE hub and connect to it.

        Make sure:
          - The hub is turned on and Bluetooth is enabled (blue light blinking).
          - Bluetooth is enabled on your Mac.
          - The hub is NOT currently connected to the SPIKE app / iPad / phone.
        """
        log.info("Scanning for LEGO SPIKE hub over BLE (this may take a few seconds)...")

        # With return_adv=True, discover() returns a dict:
        #   key: str (address/ID)
        #   value: (BLEDevice, AdvertisementData)
        results = await BleakScanner.discover(timeout=8.0, return_adv=True)

        if not results:
            raise RuntimeError(
                "No BLE devices found. Make sure Bluetooth is on and the hub is powered."
            )

        log.info("Discovered %d BLE devices:", len(results))
        for key, (dev, adv) in results.items():
            log.info(
                "  - %s (%s) service_uuids=%s",
                dev.name,
                dev.address,
                adv.service_uuids,
            )

        # --- 1) Try the classic LEGO Hub service UUID (older docs / some hubs) ---
        candidates = []
        for key, (dev, adv) in results.items():
            service_uuids = [u.lower() for u in (adv.service_uuids or [])]
            if LEGO_HUB_SERVICE_UUID.lower() in service_uuids:
                candidates.append((dev, adv))

        # --- 2) If none match by UUID, fall back to name-based matching (SPIKE Prime etc.) ---
        if not candidates:
            name_candidates = []
            for key, (dev, adv) in results.items():
                name = (dev.name or "").lower()
                if "spike" in name:
                    name_candidates.append((dev, adv))

            if not name_candidates:
                raise RuntimeError(
                    "Could not find any LEGO SPIKE hub.\n"
                    "I expected to see a device named something like 'SPIKE Prime'.\n"
                    "Make sure the hub's blue Bluetooth light is blinking and it is not "
                    "connected to the SPIKE app or another device."
                )

            # Use the first SPIKE-named device
            candidates = name_candidates

        # If there are multiple, optionally narrow by name hint
        dev_to_use = None
        if self._device_name_hint:
            hint = self._device_name_hint.lower()
            for dev, adv in candidates:
                if (dev.name or "").lower().find(hint) != -1:
                    dev_to_use = dev
                    break

        if dev_to_use is None:
            dev_to_use = candidates[0][0]

        log.info("Connecting to hub: %s (%s)", dev_to_use.name, dev_to_use.address)
        client = BleakClient(dev_to_use)
        await client.connect()
        if not client.is_connected:
            raise RuntimeError("Failed to connect to SPIKE hub over BLE")

        self._client = client
        log.info("Connected to SPIKE hub.")

    # ------------------------------------------------------------------ #
    # High-level motor commands                                          #
    # ------------------------------------------------------------------ #

    async def run_motor_for_degrees(
        self,
        port: str = "A",
        speed: int = 50,
        degrees: int = 360,
        max_power: int = 100,
    ) -> None:
        """
        Spin a single motor on the given port for a number of degrees.

        :param port: Port name (e.g. 'A').
        :param speed: Speed in percent (-100..100).
        :param degrees: Number of degrees to rotate.
        :param max_power: Max power percent (0..100).
        """
        if not self._client or not self._client.is_connected:
            raise RuntimeError("SpikeHub is not connected")

        port_id = self._port_name_to_id(port)

        # Clamp values
        speed = max(-100, min(100, int(speed)))
        max_power = max(0, min(100, int(max_power)))
        degrees = int(degrees)

        msg = self._build_single_motor_for_degrees_command(
            port_id=port_id,
            speed=speed,
            degrees=degrees,
            max_power=max_power,
        )

        log.debug("Sending motor command bytes: %s", msg)
        await self._client.write_gatt_char(LEGO_HUB_CHAR_UUID, msg, response=False)

    async def test_spin_motor_a(self) -> None:
        """
        Workshop sanity check: spin motor on port A so you know BLE + LWP are working.
        """
        log.info("Test: spinning motor on port A (slow one rotation)")
        await self.run_motor_for_degrees(port="A", speed=40, degrees=360)
        await asyncio.sleep(0.5)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _port_name_to_id(port: str) -> int:
        upper = port.upper()
        if upper not in PORT_NAME_TO_ID:
            raise ValueError(f"Unknown port name {port!r}. Expected one of {list(PORT_NAME_TO_ID)}")
        return PORT_NAME_TO_ID[upper]

    @staticmethod
    def _build_single_motor_for_degrees_command(
        port_id: int,
        speed: int,
        degrees: int,
        max_power: int,
    ) -> bytes:
        """
        Build a Port Output Command [0x81] with subcommand "StartSpeedForDegrees" [0x0B].

        Message format (LWP3, simplified):

        [0] Length (total bytes)
        [1] Hub ID            -> 0x00
        [2] Message Type      -> 0x81 (Port Output Command)
        [3] Port ID           -> e.g. 0x00 for port A
        [4] Startup/Completion info -> 0x11 (execute immediately, command feedback)
        [5] Subcommand        -> 0x0B (StartSpeedForDegrees)
        [6-9] Degrees (UInt32 LE)
        [10] Speed (SByte, -100..100)
        [11] MaxPower (UInt8, 0..100)
        [12] EndState (UInt8) -> 0x7F (brake)
        [13] UseProfile (UInt8) -> 0x00 (none)
        """

        # Degrees as little-endian unsigned 32-bit
        deg = degrees & 0xFFFFFFFF
        deg_bytes = [
            deg & 0xFF,
            (deg >> 8) & 0xFF,
            (deg >> 16) & 0xFF,
            (deg >> 24) & 0xFF,
        ]

        # Convert signed speed to byte (two’s complement)
        speed_byte = speed & 0xFF

        payload = [
            0x00,        # Hub ID
            0x81,        # Message Type: Port Output Command
            port_id,     # Port ID
            0x11,        # Startup & Completion
            0x0B,        # Subcommand: StartSpeedForDegrees
            *deg_bytes,  # Degrees
            speed_byte,  # Speed
            max_power,   # Max power
            0x7F,        # EndState: brake
            0x00,        # UseProfile: none
        ]

        length = len(payload) + 1  # include length byte itself
        return bytes([length] + payload)
