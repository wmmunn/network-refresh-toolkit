from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .models import DeviceMetadata, NeighborLink, SnapshotRecord


SUCCESS_STATES = {"complete", "completed", "done", "processed", "success", "succeeded"}
SNAPSHOT_COLLECTION_KEYS = ("items", "snapshots", "data")
DEVICE_COLLECTION_KEYS = ("items", "devices", "nodes", "data")
TOPOLOGY_COLLECTION_KEYS = ("items", "links", "edges", "connections", "adjacencies", "neighbors", "data")
NEIGHBOR_COLLECTION_KEYS = ("neighbors", "lldpNeighbors", "cdpNeighbors", "adjacencies", "links", "connections")
SNAPSHOT_ID_KEYS = ("id", "snapshotId", "snapshot_id")
SNAPSHOT_STATUS_KEYS = ("status", "state")
SNAPSHOT_SORT_KEYS = ("completedAt", "createdAt", "updatedAt", "startedAt", "timestamp")
HOSTNAME_KEYS = ("name", "hostname", "deviceName", "displayName", "label")
IP_KEYS = (
    "ipAddress",
    "primaryIp",
    "primaryIP",
    "managementIp",
    "managementIP",
    "managementIps",
    "managementIPs",
    "mgmtIp",
    "mgmtIP",
    "mgmtIps",
    "mgmtIPs",
    "ip",
)
TYPE_KEYS = ("deviceType", "type", "platform", "model", "vendorModel")
ROLE_KEYS = ("role", "deviceRole", "networkRole", "tier")
LOCATION_KEYS = ("location", "site", "idf", "closet", "building", "floor", "room", "locationName")
PROTOCOL_KEYS = ("protocol", "neighborProtocol", "discoveryProtocol", "type")
LOCAL_INTERFACE_KEYS = ("localInterface", "localPort", "interface", "interfaceName", "sourceInterface", "sourcePort")
REMOTE_INTERFACE_KEYS = ("remotePort", "remoteInterface", "neighborInterface", "neighborPort", "targetInterface", "targetPort")
NEIGHBOR_KEYS = ("neighborHostname", "neighborName", "remoteDevice", "remoteHostname", "target", "targetDevice", "deviceName")
SOURCE_DEVICE_KEYS = ("source", "sourceDevice", "localDevice", "deviceA", "from", "a")
TARGET_DEVICE_KEYS = ("target", "targetDevice", "remoteDevice", "deviceB", "to", "b")
SOURCE_PORT_ENDPOINT_KEYS = ("sourcePort", "source_port")
TARGET_PORT_ENDPOINT_KEYS = ("targetPort", "target_port")
ACTIVE_KEYS = ("active", "isActive", "up", "connected")
STATE_KEYS = ("state", "status", "operStatus")


def unwrap_collection(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def get_first_string(payload: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return None


def get_nested_first_string(payload: dict[str, Any], keys: Iterable[str]) -> str | None:
    value = get_first_string(payload, keys)
    if value:
        return value
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            nested_value = first_string_in_list(value)
            if nested_value:
                return nested_value
    for nested_key in ("metadata", "details", "properties", "attributes", "customVariables", "variables"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            value = get_nested_first_string(nested, keys)
            if value:
                return value
    return None


def first_string_in_list(values: list[Any]) -> str | None:
    for item in values:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if item is not None and not isinstance(item, (dict, list)):
            text = str(item).strip()
            if text:
                return text
        if isinstance(item, dict):
            nested = get_nested_first_string(item, ("ip", "address", "value", "ipAddress", "managementIp"))
            if nested:
                return nested
    return None


def snapshot_records(payload: Any) -> list[SnapshotRecord]:
    records: list[SnapshotRecord] = []
    for item in unwrap_collection(payload, SNAPSHOT_COLLECTION_KEYS):
        snapshot_id = get_first_string(item, SNAPSHOT_ID_KEYS)
        status = get_first_string(item, SNAPSHOT_STATUS_KEYS) or ""
        sort_value = get_first_string(item, SNAPSHOT_SORT_KEYS) or ""
        if snapshot_id:
            records.append(SnapshotRecord(snapshot_id=snapshot_id, status=status, sort_value=sort_value, payload=item))
    return records


def latest_successful_snapshot_id(payload: Any) -> str | None:
    successful = [
        record for record in snapshot_records(payload) if record.status.strip().casefold() in SUCCESS_STATES
    ]
    if not successful:
        return None
    successful.sort(key=lambda record: record.sort_value, reverse=True)
    return successful[0].snapshot_id


def device_hostname(device: dict[str, Any]) -> str | None:
    return get_nested_first_string(device, HOSTNAME_KEYS)


def find_device_by_hostname(payload: Any, hostname: str) -> dict[str, Any] | None:
    requested = hostname.strip().casefold()
    for device in unwrap_collection(payload, DEVICE_COLLECTION_KEYS):
        candidate = device_hostname(device)
        if candidate and candidate.casefold() == requested:
            return device
    return None


def device_metadata(device: dict[str, Any], requested_hostname: str) -> DeviceMetadata:
    return DeviceMetadata(
        hostname=device_hostname(device) or requested_hostname,
        ip_address=get_nested_first_string(device, IP_KEYS) or "Unknown",
        device_type=get_nested_first_string(device, TYPE_KEYS) or "Unknown",
        location=get_nested_first_string(device, LOCATION_KEYS) or "Unknown",
        role=get_nested_first_string(device, ROLE_KEYS) or "",
    )


def extract_neighbors(payload: Any, hostname: str, boundary_pattern: str) -> list[NeighborLink]:
    device = find_device_by_hostname(payload, hostname)
    candidates: list[NeighborLink] = []
    if device:
        candidates.extend(extract_inline_neighbors(device, hostname, boundary_pattern))

    candidates.extend(extract_graph_neighbors(payload, hostname, boundary_pattern))
    candidates.extend(extract_command_neighbors(payload, boundary_pattern))
    return enrich_neighbor_ips(dedupe_links(candidates), payload)


def extract_command_neighbors(payload: Any, boundary_pattern: str) -> list[NeighborLink]:
    if not isinstance(payload, dict):
        return []
    outputs = payload.get("commandOutputs")
    if not isinstance(outputs, dict):
        return []
    links: list[NeighborLink] = []
    lldp_text = outputs.get("lldp")
    if isinstance(lldp_text, str):
        links.extend(parse_lldp_detail(lldp_text, boundary_pattern))
    cdp_text = outputs.get("cdp")
    if isinstance(cdp_text, str):
        links.extend(parse_cdp_detail(cdp_text, boundary_pattern))
    return links


def extract_inline_neighbors(device: dict[str, Any], hostname: str, boundary_pattern: str) -> list[NeighborLink]:
    links: list[NeighborLink] = []
    for key in NEIGHBOR_COLLECTION_KEYS:
        value = device.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    link = link_from_neighbor_payload(item, hostname, boundary_pattern)
                    if link:
                        links.append(link)
    return links


def extract_graph_neighbors(payload: Any, hostname: str, boundary_pattern: str) -> list[NeighborLink]:
    requested = hostname.strip().casefold()
    links: list[NeighborLink] = []
    for item in unwrap_collection(payload, TOPOLOGY_COLLECTION_KEYS):
        source = endpoint_name(item, SOURCE_DEVICE_KEYS)
        target = endpoint_name(item, TARGET_DEVICE_KEYS)
        source_endpoint = port_endpoint(item, SOURCE_PORT_ENDPOINT_KEYS)
        target_endpoint = port_endpoint(item, TARGET_PORT_ENDPOINT_KEYS)
        if (not source or not target) and source_endpoint and target_endpoint:
            source = source_endpoint[0]
            target = target_endpoint[0]
        if not source or not target:
            continue
        if source.casefold() == requested:
            link = link_from_graph_payload(item, target, True, boundary_pattern, source_endpoint, target_endpoint)
        elif target.casefold() == requested:
            link = link_from_graph_payload(item, source, False, boundary_pattern, source_endpoint, target_endpoint)
        else:
            continue
        if link:
            links.append(link)
    return links


def link_from_neighbor_payload(item: dict[str, Any], hostname: str, boundary_pattern: str) -> NeighborLink | None:
    if not is_active_lldp_or_cdp(item):
        return None
    neighbor = get_nested_first_string(item, NEIGHBOR_KEYS)
    if not neighbor or neighbor.casefold() == hostname.casefold():
        return None
    local_interface = get_nested_first_string(item, LOCAL_INTERFACE_KEYS) or "Unknown"
    remote_port = get_nested_first_string(item, REMOTE_INTERFACE_KEYS) or "Unknown"
    protocol = normalized_protocol(item)
    role = get_nested_first_string(item, ROLE_KEYS) or ""
    device_type = get_nested_first_string(item, TYPE_KEYS) or ""
    return NeighborLink(
        local_interface=local_interface,
        neighbor_hostname=neighbor,
        remote_port=remote_port,
        protocol=protocol,
        neighbor_role=role,
        neighbor_type=device_type,
        is_boundary=is_boundary_neighbor(neighbor, role, device_type, boundary_pattern),
    )


def link_from_graph_payload(
    item: dict[str, Any],
    neighbor: str,
    source_is_local: bool,
    boundary_pattern: str,
    source_endpoint: tuple[str, str] | None = None,
    target_endpoint: tuple[str, str] | None = None,
) -> NeighborLink | None:
    if not is_active_lldp_or_cdp(item):
        return None
    local_keys = ("sourceInterface", "sourcePort", "localInterface", "localPort") if source_is_local else (
        "targetInterface",
        "targetPort",
        "remoteInterface",
        "remotePort",
    )
    remote_keys = ("targetInterface", "targetPort", "remoteInterface", "remotePort") if source_is_local else (
        "sourceInterface",
        "sourcePort",
        "localInterface",
        "localPort",
    )
    role = get_nested_first_string(item, ROLE_KEYS) or ""
    device_type = get_nested_first_string(item, TYPE_KEYS) or ""
    local_interface = get_nested_first_string(item, local_keys) or "Unknown"
    remote_port = get_nested_first_string(item, remote_keys) or "Unknown"
    if source_endpoint and target_endpoint:
        local_interface = source_endpoint[1] if source_is_local else target_endpoint[1]
        remote_port = target_endpoint[1] if source_is_local else source_endpoint[1]

    return NeighborLink(
        local_interface=local_interface,
        neighbor_hostname=neighbor,
        remote_port=remote_port,
        protocol=normalized_protocol(item),
        neighbor_role=role,
        neighbor_type=device_type,
        is_boundary=is_boundary_neighbor(neighbor, role, device_type, boundary_pattern),
    )


def endpoint_name(item: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            nested = get_nested_first_string(value, HOSTNAME_KEYS)
            if nested:
                return nested
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def port_endpoint(item: dict[str, Any], keys: Iterable[str]) -> tuple[str, str] | None:
    value = get_first_string(item, keys)
    if not value:
        return None
    parts = value.rsplit(maxsplit=1)
    if len(parts) != 2:
        return None
    device, interface = parts[0].strip(), parts[1].strip()
    if not device or not interface:
        return None
    return device, interface


def normalized_protocol(item: dict[str, Any]) -> str:
    protocol = get_nested_first_string(item, PROTOCOL_KEYS) or "unknown"
    lowered = protocol.casefold()
    if "lldp" in lowered:
        return "LLDP"
    if "cdp" in lowered:
        return "CDP"
    if port_endpoint(item, SOURCE_PORT_ENDPOINT_KEYS) and port_endpoint(item, TARGET_PORT_ENDPOINT_KEYS):
        return "TOPOLOGY"
    return protocol.upper()


def is_active_lldp_or_cdp(item: dict[str, Any]) -> bool:
    protocol = normalized_protocol(item)
    if protocol not in {"LLDP", "CDP", "TOPOLOGY"}:
        return False
    for key in ACTIVE_KEYS:
        value = item.get(key)
        if isinstance(value, bool) and not value:
            return False
    state = get_first_string(item, STATE_KEYS)
    if state and state.casefold() in {"down", "inactive", "disabled", "stale", "removed"}:
        return False
    return True


def is_boundary_neighbor(hostname: str, role: str, device_type: str, boundary_pattern: str) -> bool:
    pattern = re.compile(boundary_pattern, re.IGNORECASE)
    return any(pattern.search(value or "") for value in (hostname, role, device_type))


def dedupe_links(links: list[NeighborLink]) -> list[NeighborLink]:
    deduped: dict[tuple[str, str], NeighborLink] = {}
    for link in links:
        key = (
            interface_key(link.local_interface),
            short_hostname(link.neighbor_hostname).casefold(),
        )
        existing = deduped.get(key)
        if not existing or link_score(link) >= link_score(existing):
            deduped[key] = link
    return sorted(deduped.values(), key=lambda item: (not item.is_boundary, item.local_interface, item.neighbor_hostname))


def enrich_neighbor_ips(links: list[NeighborLink], payload: Any) -> list[NeighborLink]:
    device_lookup = {
        hostname.casefold(): device_metadata(device, hostname)
        for device in unwrap_collection(payload, DEVICE_COLLECTION_KEYS)
        for hostname in [device_hostname(device)]
        if hostname
    }
    enriched: list[NeighborLink] = []
    for link in links:
        metadata = device_lookup.get(link.neighbor_hostname.casefold())
        if not metadata or metadata.ip_address == "Unknown":
            enriched.append(link)
            continue
        enriched.append(
            NeighborLink(
                local_interface=link.local_interface,
                neighbor_hostname=link.neighbor_hostname,
                remote_port=link.remote_port,
                protocol=link.protocol,
                neighbor_ip=metadata.ip_address,
                neighbor_role=link.neighbor_role or metadata.role,
                neighbor_type=link.neighbor_type or metadata.device_type,
                is_boundary=link.is_boundary,
            )
        )
    return enriched


def parse_lldp_detail(text: str, boundary_pattern: str) -> list[NeighborLink]:
    links: list[NeighborLink] = []
    for block in detail_blocks(text):
        local_interface = field_value(block, "Local Intf")
        neighbor = field_value(block, "System Name")
        remote_port = field_value(block, "Port id")
        neighbor_ip = indented_ip_after(block, "Management Addresses") or first_ip(block)
        capabilities = field_value(block, "System Capabilities")
        if not local_interface or not neighbor:
            continue
        links.append(
            NeighborLink(
                local_interface=local_interface,
                neighbor_hostname=neighbor,
                remote_port=remote_port or "Unknown",
                protocol="LLDP",
                neighbor_ip=neighbor_ip or "",
                neighbor_role=capabilities or "",
                is_boundary=is_boundary_neighbor(neighbor, capabilities or "", "", boundary_pattern),
            )
        )
    return links


def parse_cdp_detail(text: str, boundary_pattern: str) -> list[NeighborLink]:
    links: list[NeighborLink] = []
    for block in re.split(r"^-{5,}\s*$", text, flags=re.MULTILINE):
        if "Device ID:" not in block:
            continue
        neighbor = field_value(block, "Device ID")
        local_interface = cdp_interface(block)
        remote_port = cdp_remote_port(block)
        neighbor_ip = first_ip(block)
        platform = platform_value(block)
        capabilities = capabilities_value(block)
        if not neighbor or not local_interface:
            continue
        links.append(
            NeighborLink(
                local_interface=local_interface,
                neighbor_hostname=neighbor,
                remote_port=remote_port or "Unknown",
                protocol="CDP",
                neighbor_ip=neighbor_ip or "",
                neighbor_role=capabilities or "",
                neighbor_type=platform or "",
                is_boundary=is_boundary_neighbor(neighbor, capabilities or "", platform or "", boundary_pattern),
            )
        )
    return links


def detail_blocks(text: str) -> list[str]:
    blocks = re.split(r"^-{5,}\s*$", text, flags=re.MULTILINE)
    return [block for block in blocks if "Local Intf:" in block or "System Name:" in block]


def field_value(block: str, label: str) -> str | None:
    match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    if match:
        value = match.group(1).strip()
        if value and "not advertised" not in value.casefold():
            return value
    return None


def first_ip(block: str) -> str | None:
    match = re.search(r"\bIP(?: address)?:\s*([0-9]+(?:\.[0-9]+){3})", block, flags=re.IGNORECASE)
    return match.group(1) if match else None


def indented_ip_after(block: str, heading: str) -> str | None:
    start = block.find(f"{heading}:")
    if start < 0:
        return None
    excerpt = block[start : start + 220]
    return first_ip(excerpt)


def cdp_interface(block: str) -> str | None:
    match = re.search(r"^Interface:\s*(.+?),\s*Port ID", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def cdp_remote_port(block: str) -> str | None:
    match = re.search(r"Port ID \(outgoing port\):\s*(.+?)\s*$", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def platform_value(block: str) -> str | None:
    match = re.search(r"^Platform:\s*(.*?)(?:,\s*Capabilities:|$)", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def capabilities_value(block: str) -> str | None:
    match = re.search(r"Capabilities:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def command_text_from_payload(payload: Any) -> str:
    if isinstance(payload, list):
        return "\n".join(str(line).rstrip("\r\n") for line in payload)
    if isinstance(payload, dict):
        lines = payload.get("lines")
        if isinstance(lines, list):
            return "\n".join(str(line).rstrip("\r\n") for line in lines)
        excerpts = payload.get("excerpts")
        if isinstance(excerpts, list):
            output_lines: list[str] = []
            for excerpt in excerpts:
                if isinstance(excerpt, dict) and isinstance(excerpt.get("lines"), list):
                    output_lines.extend(str(line).rstrip("\r\n") for line in excerpt["lines"])
            return "\n".join(output_lines)
    return ""


def short_hostname(hostname: str) -> str:
    return hostname.split(".", 1)[0]


def interface_key(interface: str) -> str:
    value = interface.strip().casefold()
    replacements = (
        ("tengigabitethernet", "te"),
        ("twentyfivegige", "twe"),
        ("twentyfivegigabitethernet", "twe"),
        ("fortygigabitethernet", "fo"),
        ("hundredgige", "hu"),
        ("gigabitethernet", "gi"),
        ("fastethernet", "fa"),
        ("ethernet", "eth"),
    )
    for long_name, short_name in replacements:
        if value.startswith(long_name):
            return short_name + value[len(long_name) :]
    return value


def link_score(link: NeighborLink) -> int:
    score = 0
    if link.protocol in {"CDP", "LLDP"}:
        score += 10
    if link.neighbor_ip:
        score += 4
    if link.remote_port and link.remote_port != "Unknown":
        score += 2
    if "." in link.neighbor_hostname:
        score += 1
    return score
