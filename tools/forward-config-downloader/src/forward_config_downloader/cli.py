from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .client import DownloaderError, ForwardClient
from .models import AuthSettings, DownloaderSettings, ExitCode
from .output import configure_logging, log_event


DEFAULT_NETWORK_ID = ""

DEFAULT_DEVICES_PATH_TEMPLATES = (
    "/networks/{network_id}/snapshots/{snapshot_id}/devices",
    "/snapshots/{snapshot_id}/devices",
    "/networks/{network_id}/devices?snapshotId={snapshot_id}",
    "/networks/{network_id}/devices?snapshot_id={snapshot_id}",
    "/networks/{network_id}/snapshots/{snapshot_id}/device-configs",
    "/networks/{network_id}/snapshots/{snapshot_id}/configs/devices",
)

DEFAULT_CONFIG_PATH_TEMPLATES = (
    "/snapshots/{snapshot_id}/files/{config_file}?lines={line_start}-{line_end}",
    "/networks/{network_id}/snapshots/{snapshot_id}/locations/{location_id}/files/{config_file}",
    "/networks/{network_id}/snapshots/{snapshot_id}/locations/{location_id}/files?file={config_file}",
    "/networks/{network_id}/snapshots/{snapshot_id}/files/{config_file}?locationId={location_id}",
    "/networks/{network_id}/snapshots/{snapshot_id}/files?locationId={location_id}&file={config_file}",
    "/snapshots/{snapshot_id}/locations/{location_id}/files/{config_file}",
    "/snapshots/{snapshot_id}/files?locationId={location_id}&file={config_file}",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/config",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/configuration",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/commands",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/commands/show%20running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/command-outputs",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/commandOutputs",
    "/snapshots/{snapshot_id}/devices/{device_name}/config",
    "/snapshots/{snapshot_id}/devices/{device_name}/configuration",
    "/snapshots/{snapshot_id}/devices/{device_name}/running-config",
    "/snapshots/{snapshot_id}/devices/{device_name}/commands/show%20running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/device-configs/{device_name}",
    "/networks/{network_id}/snapshots/{snapshot_id}/configs/{device_name}",
    "/networks/{network_id}/snapshots/{snapshot_id}/configs?deviceName={device_name}",
    "/networks/{network_id}/snapshots/{snapshot_id}/device-configs?deviceName={device_name}",
    "/networks/{network_id}/snapshots/{snapshot_id}/commands?deviceName={device_name}&command=show%20running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/command-outputs?deviceName={device_name}&command=show%20running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/commandOutputs?deviceName={device_name}&command=show%20running-config",
    "/networks/{network_id}/snapshots/{snapshot_id}/device-command-outputs?deviceName={device_name}&command=show%20running-config",
    "/snapshots/{snapshot_id}/commands?deviceName={device_name}&command=show%20running-config",
    "/snapshots/{snapshot_id}/command-outputs?deviceName={device_name}&command=show%20running-config",
    "/snapshots/{snapshot_id}/commandOutputs?deviceName={device_name}&command=show%20running-config",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download a switch running-config from the latest completed Forward Networks snapshot.",
    )
    parser.add_argument("--base-url", default=os.environ.get("FWD_BASE_URL", "https://fwd.app"))
    parser.add_argument("--api-prefix", default=os.environ.get("FWD_API_PREFIX", "/api"))
    parser.add_argument("--network-id", default=os.environ.get("FORWARD_NETWORKS_NETWORK_ID", DEFAULT_NETWORK_ID))
    parser.add_argument("--snapshot-id", help="Use a specific snapshot ID instead of automatically selecting the latest completed snapshot.")
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--location-id", help="Forward UI locationId for the device/config file, when known.")
    parser.add_argument("--config-file", help="Forward UI config file value, such as 'SWITCH,configuration.txt'.")
    parser.add_argument("--auth-mode", choices=("bearer", "basic"), default=os.environ.get("FWD_AUTH_MODE", "basic"))
    parser.add_argument("--api-token", default=os.environ.get("FWD_API_TOKEN"))
    parser.add_argument(
        "--devices-path-template",
        action="append",
        help=(
            "Override the device/config endpoint path after the API prefix. "
            "May include {network_id} and {snapshot_id}. Can be provided more than once."
        ),
    )
    parser.add_argument(
        "--config-path-template",
        action="append",
        help=(
            "Override the per-device config endpoint path after the API prefix. "
            "May include {network_id}, {snapshot_id}, and {device_name}. Can be provided more than once."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("manifests"))
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--line-page-size", type=int, default=200)
    parser.add_argument("--max-line-pages", type=int, default=500)
    return parser


def settings_from_args(args: argparse.Namespace) -> DownloaderSettings:
    auth = AuthSettings(
        mode=args.auth_mode,
        token=args.api_token,
        key=os.environ.get("FORWARD_NETWORKS_KEY"),
        secret=os.environ.get("FORWARD_NETWORKS_SECRET"),
    )
    return DownloaderSettings(
        base_url=args.base_url,
        api_prefix=args.api_prefix,
        network_id=args.network_id,
        snapshot_id=args.snapshot_id,
        hostname=args.hostname,
        location_id=args.location_id,
        config_file=args.config_file,
        devices_path_templates=tuple(args.devices_path_template or DEFAULT_DEVICES_PATH_TEMPLATES),
        config_path_templates=tuple(args.config_path_template or DEFAULT_CONFIG_PATH_TEMPLATES),
        output_dir=args.output_dir,
        logs_dir=args.logs_dir,
        timeout_seconds=args.timeout_seconds,
        line_page_size=args.line_page_size,
        max_line_pages=args.max_line_pages,
        auth=auth,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = settings_from_args(args)
    log_path = configure_logging(settings.logs_dir)

    try:
        validate_settings(settings)
        result = ForwardClient(settings).download()
    except DownloaderError as exc:
        log_event(logging.ERROR, "download_failed", exit_code=int(exc.exit_code), error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Log: {log_path}", file=sys.stderr)
        return int(exc.exit_code)

    print(f"Wrote running-config for {result.hostname} from snapshot {result.snapshot_id}")
    print(result.output_path)
    print(f"Log: {log_path}")
    return int(ExitCode.SUCCESS)


def validate_settings(settings: DownloaderSettings) -> None:
    if not settings.network_id:
        raise DownloaderError(
            ExitCode.CONFIG_ERROR,
            "Missing Forward Networks network ID. Set FORWARD_NETWORKS_NETWORK_ID or pass --network-id.",
        )
    if settings.auth.mode == "basic" and (not settings.auth.key or not settings.auth.secret):
        raise DownloaderError(
            ExitCode.CONFIG_ERROR,
            "Missing Forward Networks credentials. Set FORWARD_NETWORKS_KEY and FORWARD_NETWORKS_SECRET.",
        )
    if settings.auth.mode == "bearer" and not settings.auth.token:
        raise DownloaderError(ExitCode.CONFIG_ERROR, "Bearer auth requires FWD_API_TOKEN.")


def validate_credentials(auth: AuthSettings) -> None:
    placeholder = DownloaderSettings(
        base_url="",
        api_prefix="",
        network_id="placeholder",
        snapshot_id=None,
        hostname="",
        location_id=None,
        config_file=None,
        devices_path_templates=(),
        config_path_templates=(),
        output_dir=Path("."),
        logs_dir=Path("."),
        timeout_seconds=30.0,
        line_page_size=200,
        max_line_pages=500,
        auth=auth,
    )
    validate_settings(placeholder)


if __name__ == "__main__":
    raise SystemExit(main())
