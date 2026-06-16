from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from .client import ForwardTopologyClient, MapperError
from .models import AuthSettings, ExitCode, MapperSettings
from .render import write_blueprint


DEFAULT_NETWORK_ID = ""
DEFAULT_BOUNDARY_PATTERN = r"(dist|distribution|core|router|rtr|gw|gateway)"
DEFAULT_TOPOLOGY_PATH_TEMPLATES = (
    "/networks/{network_id}/snapshots/{snapshot_id}/topology",
    "/snapshots/{snapshot_id}/topology",
    "/networks/{network_id}/snapshots/{snapshot_id}/links",
    "/snapshots/{snapshot_id}/links",
    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/neighbors",
    "/snapshots/{snapshot_id}/devices/{device_name}/neighbors",
)
DEFAULT_DEVICES_PATH_TEMPLATES = (
    "/networks/{network_id}/snapshots/{snapshot_id}/devices",
    "/snapshots/{snapshot_id}/devices",
    "/networks/{network_id}/devices?snapshotId={snapshot_id}",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a Markdown switch-refresh topology blueprint and SVG map from Forward Networks data.",
    )
    parser.add_argument("--hostname", required=True, help="Target access switch hostname.")
    parser.add_argument("--base-url", default=os.environ.get("FWD_BASE_URL", "https://fwd.app"))
    parser.add_argument("--api-prefix", default=os.environ.get("FWD_API_PREFIX", "/api"))
    parser.add_argument("--network-id", default=os.environ.get("FORWARD_NETWORKS_NETWORK_ID", DEFAULT_NETWORK_ID))
    parser.add_argument("--snapshot-id", help="Use a specific snapshot ID instead of the latest completed snapshot.")
    parser.add_argument("--auth-mode", choices=("bearer", "basic"), default=os.environ.get("FWD_AUTH_MODE", "basic"))
    parser.add_argument("--api-token", default=os.environ.get("FWD_API_TOKEN"))
    parser.add_argument("--boundary-pattern", default=DEFAULT_BOUNDARY_PATTERN)
    parser.add_argument("--local-payload", type=Path, help="Read a sanitized local topology JSON payload instead of calling the API.")
    parser.add_argument("--topology-path-template", action="append", help="Override topology endpoint path template.")
    parser.add_argument("--devices-path-template", action="append", help="Override devices endpoint path template.")
    parser.add_argument("--output-dir", type=Path, default=Path("..") / "docs")
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser


def settings_from_args(args: argparse.Namespace) -> MapperSettings:
    return MapperSettings(
        base_url=args.base_url,
        api_prefix=args.api_prefix,
        network_id=args.network_id,
        snapshot_id=args.snapshot_id,
        hostname=args.hostname,
        topology_path_templates=tuple(args.topology_path_template or DEFAULT_TOPOLOGY_PATH_TEMPLATES),
        devices_path_templates=tuple(args.devices_path_template or DEFAULT_DEVICES_PATH_TEMPLATES),
        output_dir=args.output_dir,
        logs_dir=args.logs_dir,
        timeout_seconds=args.timeout_seconds,
        boundary_pattern=args.boundary_pattern,
        local_payload=args.local_payload,
        auth=AuthSettings(
            mode=args.auth_mode,
            token=args.api_token,
            key=os.environ.get("FORWARD_NETWORKS_KEY"),
            secret=os.environ.get("FORWARD_NETWORKS_SECRET"),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = settings_from_args(args)
    log_path = configure_logging(settings.logs_dir)
    exit_code = int(ExitCode.SUCCESS)
    try:
        validate_settings(settings)
        blueprint = ForwardTopologyClient(settings).build_blueprint()
        result = write_blueprint(blueprint, settings.output_dir)
    except MapperError as exc:
        logging.error("mapper_failed exit_code=%s error=%s", int(exc.exit_code), exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Log: {log_path}", file=sys.stderr)
        exit_code = int(exc.exit_code)
        logging.shutdown()
        return exit_code
    except OSError as exc:
        logging.error("output_failed error=%s", exc)
        print(f"ERROR: Could not write output file: {exc}", file=sys.stderr)
        print(f"Log: {log_path}", file=sys.stderr)
        exit_code = int(ExitCode.OUTPUT_FAILED)
        logging.shutdown()
        return exit_code

    print(f"Wrote topology blueprint for {blueprint.target.hostname} from snapshot {blueprint.snapshot_id}")
    print(result.markdown_path)
    print(result.svg_path)
    print(f"Log: {log_path}")
    logging.shutdown()
    return exit_code


def validate_settings(settings: MapperSettings) -> None:
    if not settings.network_id and not settings.local_payload:
        raise MapperError(ExitCode.CONFIG_ERROR, "Missing Forward Networks network ID. Set FORWARD_NETWORKS_NETWORK_ID or pass --network-id.")
    if settings.local_payload:
        if not settings.local_payload.exists():
            raise MapperError(ExitCode.CONFIG_ERROR, f"Local payload not found: {settings.local_payload}")
        return
    if settings.auth.mode == "basic" and (not settings.auth.key or not settings.auth.secret):
        raise MapperError(ExitCode.CONFIG_ERROR, "Missing Forward Networks credentials. Set FORWARD_NETWORKS_KEY and FORWARD_NETWORKS_SECRET.")
    if settings.auth.mode == "bearer" and not settings.auth.token:
        raise MapperError(ExitCode.CONFIG_ERROR, "Bearer auth requires FWD_API_TOKEN.")


def configure_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"forward-topology-mapper-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8", force=True)
    return log_path


if __name__ == "__main__":
    raise SystemExit(main())
