from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[-_]?key|api[-_]?token|authorization|bearer|credential|password|secret|token)",
    re.IGNORECASE,
)
AUTH_HEADER_PATTERN = re.compile(
    r"\b(Authorization\s*[:=]\s*)(Bearer|Basic)\s+[^,\s;]+",
    re.IGNORECASE,
)
INLINE_SECRET_PATTERN = re.compile(
    r"\b(api[-_]?key|api[-_]?token|password|secret|token)\s*[:=]\s*([^,&\s;]+)",
    re.IGNORECASE,
)


def safe_filename(value: str) -> str:
    cleaned = SAFE_FILENAME_PATTERN.sub("_", value.strip()).strip("._")
    return cleaned or "device"


def write_config(output_dir: Path, hostname: str, snapshot_id: str, config_text: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_filename(hostname)}__snapshot-{safe_filename(snapshot_id)}__running-config.txt"
    output_path = output_dir / filename
    output_path.write_text(config_text, encoding="utf-8", newline="\n")
    return output_path


def configure_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = logs_dir / f"forward-config-downloader-{timestamp}.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
        force=True,
    )
    return log_path


def redact_sensitive_text(value: str) -> str:
    redacted = AUTH_HEADER_PATTERN.sub(r"\1\2 <redacted>", value)
    redacted = INLINE_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    return _redact_sensitive_query_values(redacted)


def _redact_sensitive_query_values(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value

    if not parts.query:
        return value

    query_items = []
    changed = False
    for key, item_value in parse_qsl(parts.query, keep_blank_values=True):
        if SENSITIVE_KEY_PATTERN.search(key):
            query_items.append((key, "<redacted>"))
            changed = True
        else:
            query_items.append((key, item_value))

    if not changed:
        return value

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query_items),
            parts.fragment,
        )
    )


def sanitize_for_log(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        safe_mapping = {}
        for key, item_value in value.items():
            key_text = str(key)
            safe_mapping[key_text] = "<redacted>" if SENSITIVE_KEY_PATTERN.search(key_text) else sanitize_for_log(item_value)
        return safe_mapping
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [sanitize_for_log(item) for item in value]
    return value


def log_event(level: int, event: str, **fields: Any) -> None:
    safe_fields = {
        key: "<redacted>" if SENSITIVE_KEY_PATTERN.search(key) else sanitize_for_log(value)
        for key, value in fields.items()
        if value is not None
    }
    logging.log(level, "%s %s", event, json.dumps(safe_fields, sort_keys=True))
