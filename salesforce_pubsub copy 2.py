# salesforce_pubsub.py
#
# Reads Salesforce OAuth token info from sf_token_info.json (created by sf_login.py)
# and exposes an async generator subscribe_to_commands() that yields Command__c
# values from the LEGO_Command__e platform event via Pub/Sub API.
#
# It also provides helpers to:
#   - Reuse REST auth (access token + instance URL)
#   - Publish robot status back to Salesforce via a Platform Event
#     (e.g., LEGO_Robot_Status__e).
#
# Existing behavior is preserved; new helpers are purely additive.

import asyncio
import io
import json
import logging
import queue
import threading
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import grpc
from fastavro import parse_schema, schemaless_reader
import requests  # NEW: used for simple REST calls back to Salesforce

import pubsub_api_pb2 as pubsub
import pubsub_api_pb2_grpc as pubsub_grpc

# Add near the other imports at the top of salesforce_pubsub.py
from typing import Any

try:
    import requests  # Only needed if you actually publish status events
except ImportError:
    requests = None  # We'll guard usage so existing logic never breaks


# Optional: API version and status event name for robot feedback
API_VERSION = "61.0"  # Adjust to your org's API version if needed
ROBOT_STATUS_EVENT = "LEGO_Robot_Status__e"  # Or whatever you name your status PE

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

TOKEN_FILE = Path("sf_token_info.json")
PUBSUB_ENDPOINT = "api.pubsub.salesforce.com:7443"
TOPIC_NAME = "/event/LEGO_Command__e"  # adjust if needed

# NEW: REST API version & status event name for robot telemetry
REST_API_VERSION = "61.0"  # adjust if your org is on a different version
ROBOT_STATUS_EVENT_API_NAME = "LEGO_Robot_Status__e"

_log = logging.getLogger(__name__)

# These globals will be populated after we load the token file
AUTH_METADATA = None
_schema_cache: Dict[str, Dict] = {}
_last_replay_id: Optional[bytes] = None
_semaphore = threading.Semaphore(0)


# -------------------------------------------------------------------
# Token file / auth metadata
# -------------------------------------------------------------------

def _load_token_file() -> Dict:
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"{TOKEN_FILE} not found. Run 'python sf_login.py' first to generate it."
        )
    data = json.loads(TOKEN_FILE.read_text())
    required_keys = ["access_token", "instance_url", "org_id"]
    for k in required_keys:
        if k not in data:
            raise ValueError(f"{TOKEN_FILE} missing '{k}' – run sf_login.py again.")
    return data


def _build_auth_metadata_from_token() -> tuple:
    data = _load_token_file()
    access_token = data["access_token"]
    instance_url = data["instance_url"]
    org_id = data["org_id"]

    return (
        ("accesstoken", access_token),
        ("instanceurl", instance_url),
        ("tenantid", org_id),
    )


def _ensure_auth_metadata():
    global AUTH_METADATA
    if AUTH_METADATA is None:
        AUTH_METADATA = _build_auth_metadata_from_token()
        _log.info("Loaded Salesforce auth metadata from %s", TOKEN_FILE)

# -------------------------------------------------------------------
# Optional: Publish platform events back to Salesforce (robot status)
# -------------------------------------------------------------------

async def publish_platform_event(
    sobject_name: str,
    fields: Dict[str, Any],
) -> None:
    """
    Publish a platform event (or any sObject) via REST using the same
    sf_token_info.json used for Pub/Sub.

    This is optional and only used if you explicitly call it. It requires
    the 'requests' library. If requests is not installed, we log an error
    and return without breaking anything else.
    """
    if requests is None:
        _log.error(
            "Cannot publish platform event %s – 'requests' is not installed. "
            "Run 'pip install requests' in your venv if you want status publishing.",
            sobject_name,
        )
        return

    # Reuse the token file we already have
    data = _load_token_file()
    access_token = data["access_token"]
    instance_url = data["instance_url"]

    url = f"{instance_url}/services/data/v{API_VERSION}/sobjects/{sobject_name}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    def _do_post():
        resp = requests.post(url, headers=headers, json=fields, timeout=10)
        return resp.status_code, resp.text

    # Run the blocking HTTP call in a thread so we don't block the event loop
    import asyncio

    status_code, body = await asyncio.to_thread(_do_post)

    if 200 <= status_code < 300:
        _log.info(
            "Published %s platform event successfully: HTTP %s, body=%s",
            sobject_name,
            status_code,
            body,
        )
    else:
        _log.error(
            "Failed to publish %s platform event: HTTP %s, body=%s",
            sobject_name,
            status_code,
            body,
        )


async def publish_robot_status(
    status_text: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Convenience wrapper for sending the robot's status back to Salesforce
    as a platform event.

    Expects a Platform Event like LEGO_Robot_Status__e with at least:
      - Status__c (Text)
      - maybe Command__c, Mode__c, Zone__c, etc., if you want.

    Example usage from your bridge:
        await publish_robot_status("ZONE_REACHED:RECYCLING_OK", {"Mode__c": "RECYCLING"})
    """
    fields: Dict[str, Any] = {"Status__c": status_text}
    if extra_fields:
        fields.update(extra_fields)

    await publish_platform_event(ROBOT_STATUS_EVENT, fields)



# -------------------------------------------------------------------
# NEW: REST helpers (for sending robot status back to Salesforce)
# -------------------------------------------------------------------

def get_rest_auth() -> Dict[str, str]:
    """
    Convenience helper to reuse the same token info for REST calls.

    Returns a dict with:
      - access_token
      - instance_url
      - org_id
    """
    data = _load_token_file()
    return {
        "access_token": data["access_token"],
        "instance_url": data["instance_url"],
        "org_id": data["org_id"],
    }


def publish_robot_status(
    command: Optional[str],
    phase: str,
    message: str,
    board_position: Optional[str] = None,
    extra_fields: Optional[Dict[str, str]] = None,
) -> None:
    """
    Publish a simple status event back into Salesforce so Flows / Agents / Dashboards
    can see what the robot is doing.

    This assumes you've created a Platform Event called LEGO_Robot_Status__e with fields:
      - Command__c (Text)
      - Phase__c (Text)
      - Message__c (Long Text)
      - Board_Position__c (Text)  [optional]

    Additional fields can be passed via extra_fields (e.g. case Id).
    """

    try:
        auth = get_rest_auth()
    except Exception as exc:
        _log.error("Unable to load REST auth from token file: %s", exc)
        return

    access_token = auth["access_token"]
    instance_url = auth["instance_url"]

    url = (
        f"{instance_url}/services/data/v{REST_API_VERSION}"
        f"/sobjects/{ROBOT_STATUS_EVENT_API_NAME}/"
    )

    payload: Dict[str, str] = {
        "Phase__c": phase,
        "Message__c": message,
    }

    if command:
        payload["Command__c"] = command

    if board_position:
        payload["Board_Position__c"] = board_position

    if extra_fields:
        payload.update(extra_fields)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code >= 300:
            _log.warning(
                "Failed to publish LEGO_Robot_Status__e (%s): %s",
                resp.status_code,
                resp.text,
            )
        else:
            _log.info(
                "Published LEGO_Robot_Status__e: command=%r phase=%r board=%r",
                command,
                phase,
                board_position,
            )
    except Exception as exc:
        _log.error("Error sending robot status event: %s", exc)


# -------------------------------------------------------------------
# Schema helpers
# -------------------------------------------------------------------

def _get_avro_schema_for_topic(stub: pubsub_grpc.PubSubStub, topic_name: str) -> Dict:
    """
    Fetch the latest Avro schema for a topic using GetTopic + GetSchema.
    """
    global _schema_cache

    topic_info = stub.GetTopic(
        pubsub.TopicRequest(topic_name=topic_name),
        metadata=AUTH_METADATA,
    )
    schema_id = topic_info.schema_id

    if schema_id in _schema_cache:
        return _schema_cache[schema_id]

    schema_info = stub.GetSchema(
        pubsub.SchemaRequest(schema_id=schema_id),
        metadata=AUTH_METADATA,
    )

    schema_json = schema_info.schema_json
    schema_dict = json.loads(schema_json)
    parsed_schema = parse_schema(schema_dict)

    result = {"id": schema_id, "parsed": parsed_schema}
    _schema_cache[schema_id] = result
    _log.info("Fetched Avro schema %s for topic %s", schema_id, topic_name)

    return result


def _decode_event_payload(avro_schema: Dict, consumer_event: pubsub.ConsumerEvent) -> Dict:
    """
    Decode a single ConsumerEvent's inner producer event payload using fastavro.

    consumer_event.event is the ProducerEvent that actually holds:
      - payload (bytes)
      - schema_id (string)
    """
    inner = consumer_event.event  # this matches evt.event in the Salesforce sample

    bio = io.BytesIO(inner.payload)
    record = schemaless_reader(bio, avro_schema["parsed"])
    return record


# -------------------------------------------------------------------
# Subscribe (background worker)
# -------------------------------------------------------------------

def _fetch_request_stream(topic_name: str):
    global _last_replay_id

    _semaphore.acquire(False)  # drain
    _semaphore.release()

    while True:
        _semaphore.acquire()
        req = pubsub.FetchRequest(
            topic_name=topic_name,
            num_requested=1,
        )
        if _last_replay_id is not None:
            req.replay_id = _last_replay_id
        yield req


def _subscription_worker(cmd_queue: "queue.Queue[str]"):
    global _last_replay_id, AUTH_METADATA

    _ensure_auth_metadata()

    creds = grpc.ssl_channel_credentials()
    channel = grpc.secure_channel(PUBSUB_ENDPOINT, creds)
    stub = pubsub_grpc.PubSubStub(channel)

    topic_schema = _get_avro_schema_for_topic(stub, TOPIC_NAME)

    _log.info("Subscribing to %s on %s", TOPIC_NAME, PUBSUB_ENDPOINT)

    fetch_stream = _fetch_request_stream(TOPIC_NAME)
    response_stream = stub.Subscribe(fetch_stream, metadata=AUTH_METADATA)

    for fetch_response in response_stream:
        _semaphore.release()

        for event in fetch_response.events:
            _last_replay_id = event.replay_id

            try:
                record = _decode_event_payload(topic_schema, event)
            except Exception as exc:
                _log.exception("Failed to decode event payload: %s", exc)
                continue

            _log.info("Full decoded event record: %s", record)

            command = record.get("Command__c")
            if command:
                _log.info("Received LEGO command from Salesforce: %s", command)
                cmd_queue.put(command)


# -------------------------------------------------------------------
# Async façade
# -------------------------------------------------------------------

async def subscribe_to_commands() -> AsyncIterator[str]:
    """
    Async generator that yields command strings (e.g. "ESCALATE", "TIER_1")
    coming from the LEGO_Command__e platform event.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    _ensure_auth_metadata()

    loop = asyncio.get_running_loop()
    cmd_queue: "queue.Queue[str]" = queue.Queue()

    worker = threading.Thread(
        target=_subscription_worker,
        args=(cmd_queue,),
        daemon=True,
    )
    worker.start()

    _log.info("Pub/Sub subscription thread started, now yielding commands...")

    while True:
        command = await asyncio.to_thread(cmd_queue.get)
        yield command


# -------------------------------------------------------------------
# Test harness (optional)
# -------------------------------------------------------------------

async def _test_read_commands():
    async for cmd in subscribe_to_commands():
        print(f"Command from Salesforce: {cmd}")


if __name__ == "__main__":
    asyncio.run(_test_read_commands())
