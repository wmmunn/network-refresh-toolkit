from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Literal


AuthMode = Literal["bearer", "basic"]


class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIG_ERROR = 1
    REQUEST_FAILED = 3
    SNAPSHOT_NOT_FOUND = 4
    DEVICE_NOT_FOUND = 5
    CONFIG_NOT_FOUND = 6
    OUTPUT_FAILED = 7


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    token: str | None = None
    key: str | None = None
    secret: str | None = None


@dataclass(frozen=True)
class DownloaderSettings:
    base_url: str
    api_prefix: str
    network_id: str
    snapshot_id: str | None
    hostname: str
    location_id: str | None
    config_file: str | None
    devices_path_templates: tuple[str, ...]
    config_path_templates: tuple[str, ...]
    output_dir: Path
    logs_dir: Path
    timeout_seconds: float
    line_page_size: int
    max_line_pages: int
    auth: AuthSettings


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    status: str
    sort_value: str
    payload: dict


@dataclass(frozen=True)
class DownloadResult:
    hostname: str
    snapshot_id: str
    output_path: Path
