from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal


AuthMode = Literal["bearer", "basic"]


class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIG_ERROR = 1
    REQUEST_FAILED = 3
    SNAPSHOT_NOT_FOUND = 4
    DEVICE_NOT_FOUND = 5
    TOPOLOGY_NOT_FOUND = 6
    OUTPUT_FAILED = 7


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    token: str | None = None
    key: str | None = None
    secret: str | None = None


@dataclass(frozen=True)
class MapperSettings:
    base_url: str
    api_prefix: str
    network_id: str
    snapshot_id: str | None
    hostname: str
    topology_path_templates: tuple[str, ...]
    devices_path_templates: tuple[str, ...]
    output_dir: Path
    logs_dir: Path
    timeout_seconds: float
    boundary_pattern: str
    local_payload: Path | None
    auth: AuthSettings


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    status: str
    sort_value: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DeviceMetadata:
    hostname: str
    ip_address: str
    device_type: str
    location: str
    role: str


@dataclass(frozen=True)
class NeighborLink:
    local_interface: str
    neighbor_hostname: str
    remote_port: str
    protocol: str
    neighbor_ip: str = ""
    neighbor_role: str = ""
    neighbor_type: str = ""
    is_boundary: bool = False


@dataclass(frozen=True)
class TopologyBlueprint:
    target: DeviceMetadata
    snapshot_id: str
    boundary_pattern: str
    neighbors: tuple[NeighborLink, ...]


@dataclass(frozen=True)
class WriteResult:
    markdown_path: Path
    svg_path: Path
