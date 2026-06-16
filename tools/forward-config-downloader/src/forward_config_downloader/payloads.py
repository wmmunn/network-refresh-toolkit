from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import SnapshotRecord


SUCCESS_STATES = {
    "complete",
    "completed",
    "done",
    "processed",
    "success",
    "succeeded",
}

SNAPSHOT_COLLECTION_KEYS = ("items", "snapshots", "data")
DEVICE_COLLECTION_KEYS = ("items", "devices", "data")
SNAPSHOT_ID_KEYS = ("id", "snapshotId", "snapshot_id")
SNAPSHOT_STATUS_KEYS = ("status", "state")
SNAPSHOT_SORT_KEYS = ("completedAt", "createdAt", "updatedAt", "startedAt", "timestamp")
HOSTNAME_KEYS = ("name", "hostname", "deviceName", "displayName")
CONFIG_PATHS = (
    ("config", "rawText"),
    ("config", "runningConfig"),
    ("runningConfig",),
    ("rawText",),
    ("configuration",),
    ("configText",),
)
COMMAND_OUTPUT_COLLECTION_KEYS = ("commandOutputs", "commands", "outputs")
COMMAND_NAME_KEYS = ("command", "name", "title")
COMMAND_TEXT_KEYS = ("output", "text", "rawText", "value", "result")
RUNNING_CONFIG_COMMANDS = {"show running-config", "show run", "running-config"}
CONFIG_TEXT_KEY_NAMES = {
    "config",
    "configuration",
    "configtext",
    "rawconfig",
    "rawtext",
    "runningconfig",
}


def unwrap_collection(payload: Any, keys: Iterable[str]) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def get_first_string(payload: dict, keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            value_text = str(value).strip()
            if value_text:
                return value_text
    return None


def get_path_string(payload: dict, path: tuple[str, ...]) -> str | None:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if isinstance(current, str) and current.strip():
        return current
    return None


def snapshot_records(payload: Any) -> list[SnapshotRecord]:
    records: list[SnapshotRecord] = []
    for item in unwrap_collection(payload, SNAPSHOT_COLLECTION_KEYS):
        snapshot_id = get_first_string(item, SNAPSHOT_ID_KEYS)
        status = get_first_string(item, SNAPSHOT_STATUS_KEYS) or ""
        sort_value = get_first_string(item, SNAPSHOT_SORT_KEYS) or ""
        if snapshot_id:
            records.append(
                SnapshotRecord(
                    snapshot_id=snapshot_id,
                    status=status,
                    sort_value=sort_value,
                    payload=item,
                )
            )
    return records


def latest_successful_snapshot_id(payload: Any) -> str | None:
    successful = [
        record
        for record in snapshot_records(payload)
        if record.status.strip().casefold() in SUCCESS_STATES
    ]
    if not successful:
        return None
    successful.sort(key=lambda record: record.sort_value, reverse=True)
    return successful[0].snapshot_id


def device_hostname(device: dict) -> str | None:
    return get_first_string(device, HOSTNAME_KEYS)


def find_device_by_hostname(payload: Any, hostname: str) -> dict | None:
    requested = hostname.strip().casefold()
    for device in unwrap_collection(payload, DEVICE_COLLECTION_KEYS):
        candidate = device_hostname(device)
        if candidate and candidate.casefold() == requested:
            return device
    return None


def extract_running_config(device: dict) -> str | None:
    if isinstance(device, str) and looks_like_config_text(device):
        return normalize_config_text(device)

    if isinstance(device, list):
        text = config_text_from_string_list(device)
        if text:
            return normalize_config_text(text)
        return None

    if not isinstance(device, dict):
        return None

    for path in CONFIG_PATHS:
        value = get_path_string(device, path)
        if value:
            return normalize_config_text(value)

    for collection_key in COMMAND_OUTPUT_COLLECTION_KEYS:
        values = device.get(collection_key)
        value = extract_running_config_from_command_payload(values)
        if value:
            return value

    value = find_config_text_recursively(device)
    if value:
        return value

    return None


def extract_running_config_from_command_payload(payload: Any) -> str | None:
    if isinstance(payload, list):
        for item in payload:
            value = extract_running_config_from_command_payload(item)
            if value:
                return value
        return None

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.strip().casefold() in RUNNING_CONFIG_COMMANDS:
                text = first_text_value(value)
                if text:
                    return normalize_config_text(text)

        command_name = get_first_string(payload, COMMAND_NAME_KEYS)
        if command_name and command_name.strip().casefold() in RUNNING_CONFIG_COMMANDS:
            text = first_text_value(payload)
            if text:
                return normalize_config_text(text)

        for value in payload.values():
            nested = extract_running_config_from_command_payload(value)
            if nested:
                return nested

    return None


def first_text_value(payload: Any) -> str | None:
    if isinstance(payload, str) and looks_like_config_text(payload):
        return payload
    if isinstance(payload, dict):
        for key in COMMAND_TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and looks_like_config_text(value):
                return value
        for value in payload.values():
            nested = first_text_value(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = first_text_value(item)
            if nested:
                return nested
    return None


def find_config_text_recursively(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = key.replace("_", "").replace("-", "").casefold()
            if normalized_key in CONFIG_TEXT_KEY_NAMES and isinstance(value, str) and looks_like_config_text(value):
                return normalize_config_text(value)
            nested = find_config_text_recursively(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = find_config_text_recursively(item)
            if nested:
                return nested
    return None


def looks_like_config_text(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lowered = text.casefold()
    return "\n" in text or lowered.startswith("hostname ") or "hostname " in lowered


def config_text_from_string_list(payload: list[Any]) -> str | None:
    if not payload or not all(isinstance(item, str) for item in payload):
        return None

    lines = [line.rstrip("\r\n") for line in payload]
    if not looks_like_config_lines(lines):
        return None
    return "\n".join(lines)


def looks_like_config_lines(lines: list[str]) -> bool:
    normalized = [line.strip().casefold() for line in lines if line.strip()]
    if not normalized:
        return False

    config_prefixes = (
        "!",
        "#",
        "aaa ",
        "archive",
        "banner ",
        "boot ",
        "class-map ",
        "crypto ",
        "enable ",
        "end",
        "hostname ",
        "interface ",
        "ip ",
        "ipv6 ",
        "line ",
        "logging ",
        "ntp ",
        "policy-map ",
        "router ",
        "service ",
        "snmp-server ",
        "spanning-tree ",
        "username ",
        "version ",
        "vlan ",
        "vrf ",
    )
    hits = sum(1 for line in normalized if line.startswith(config_prefixes))
    has_device_config_anchor = any(line.startswith(("hostname ", "interface ", "version ")) for line in normalized)
    return has_device_config_anchor and hits >= 2


def payload_shape(payload: Any, depth: int = 0, max_depth: int = 4) -> Any:
    if depth >= max_depth:
        return type(payload).__name__
    if isinstance(payload, dict):
        return {
            key: payload_shape(value, depth + 1, max_depth)
            for key, value in sorted(payload.items(), key=lambda item: item[0])
        }
    if isinstance(payload, list):
        if not payload:
            return []
        return [payload_shape(payload[0], depth + 1, max_depth)]
    return type(payload).__name__


def normalize_config_text(config_text: str) -> str:
    normalized = config_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized + "\n"
