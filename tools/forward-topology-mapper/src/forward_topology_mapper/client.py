from __future__ import annotations

import json
import logging
import base64
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

try:
    import requests
    from requests import Session
    from requests.auth import HTTPBasicAuth
    from requests.exceptions import RequestException
except ImportError:  # pragma: no cover
    requests = None
    Session = Any
    HTTPBasicAuth = None
    RequestException = Exception

from .models import MapperSettings, TopologyBlueprint, ExitCode
from .payloads import (
    command_text_from_payload,
    device_metadata,
    extract_neighbors,
    find_device_by_hostname,
    latest_successful_snapshot_id,
)


class MapperError(Exception):
    def __init__(self, exit_code: ExitCode, message: str, status_code: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.status_code = status_code


class ForwardTopologyClient:
    def __init__(self, settings: MapperSettings, session: Session | None = None):
        self.settings = settings
        self.session = session or (requests.Session() if requests is not None else None)
        if self.session is not None:
            self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        if not settings.local_payload:
            self._apply_auth()

    def _apply_auth(self) -> None:
        auth = self.settings.auth
        if auth.mode == "bearer":
            if not auth.token:
                raise MapperError(ExitCode.CONFIG_ERROR, "Bearer auth requires FWD_API_TOKEN or --api-token.")
            if self.session is not None:
                self.session.headers.update({"Authorization": f"Bearer {auth.token}"})
            return
        if not auth.key or not auth.secret:
            raise MapperError(
                ExitCode.CONFIG_ERROR,
                "Basic auth requires FORWARD_NETWORKS_KEY and FORWARD_NETWORKS_SECRET.",
            )
        if self.session is not None:
            self.session.auth = HTTPBasicAuth(auth.key, auth.secret) if HTTPBasicAuth else (auth.key, auth.secret)

    def snapshots_url(self) -> str:
        return self._url("/networks/{network_id}/snapshots")

    def devices_urls(self, snapshot_id: str) -> list[str]:
        return [self._url(template, snapshot_id=snapshot_id) for template in self.settings.devices_path_templates]

    def topology_urls(self, snapshot_id: str) -> list[str]:
        return [
            self._url(template, snapshot_id=snapshot_id, device_name=self.settings.hostname)
            for template in self.settings.topology_path_templates
        ]

    def command_file_urls(self, snapshot_id: str) -> list[tuple[str, str]]:
        return [
            ("lldp", self._url("/snapshots/{snapshot_id}/files/{file_name}?lines=0-9999", snapshot_id=snapshot_id, file_name=f"{self.settings.hostname},lldp.txt")),
            ("cdp", self._url("/snapshots/{snapshot_id}/files/{file_name}?lines=0-9999", snapshot_id=snapshot_id, file_name=f"{self.settings.hostname},cdp.txt")),
        ]

    def _url(self, path_template: str, **values: str) -> str:
        quoted = {"network_id": quote(self.settings.network_id, safe="")}
        quoted.update({key: quote(value, safe="" if key != "file_name" else ",") for key, value in values.items()})
        base_url = self.settings.base_url.rstrip("/")
        prefix = self.settings.api_prefix.strip("/")
        path = path_template.format(**quoted).lstrip("/")
        if prefix:
            return f"{base_url}/{prefix}/{path}"
        return f"{base_url}/{path}"

    def get_payload(self, url: str) -> Any:
        if self.session is None:
            return self.get_payload_with_urllib(url)
        try:
            response = self.session.get(url, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            raise MapperError(ExitCode.REQUEST_FAILED, f"API request failed: {exc}", status_code=status_code) from exc
        except ValueError as exc:
            raise MapperError(ExitCode.REQUEST_FAILED, f"API response was not valid JSON: {exc}") from exc

    def get_payload_with_urllib(self, url: str) -> Any:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth = self.settings.auth
        if auth.mode == "bearer" and auth.token:
            headers["Authorization"] = f"Bearer {auth.token}"
        elif auth.mode == "basic" and auth.key and auth.secret:
            raw = f"{auth.key}:{auth.secret}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")

        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise MapperError(ExitCode.REQUEST_FAILED, f"API request failed: HTTP {exc.code} {exc.reason}", status_code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise MapperError(ExitCode.REQUEST_FAILED, f"API request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except ValueError as exc:
            raise MapperError(ExitCode.REQUEST_FAILED, f"API response was not valid JSON: {exc}") from exc

    def get_payload_from_candidates(self, urls: list[str], label: str) -> Any:
        not_found: list[str] = []
        last_error: MapperError | None = None
        for url in urls:
            try:
                return self.get_payload(url)
            except MapperError as exc:
                last_error = exc
                if exc.exit_code == ExitCode.REQUEST_FAILED and exc.status_code == 404:
                    not_found.append(url)
                    logging.warning("%s_endpoint_not_found %s", label, json.dumps({"url": url}))
                    continue
                raise
        raise MapperError(
            ExitCode.REQUEST_FAILED,
            f"All candidate {label} endpoints returned 404. Tried: {'; '.join(not_found)}",
            status_code=404,
        ) from last_error

    def build_blueprint(self) -> TopologyBlueprint:
        if self.settings.local_payload:
            payload = json.loads(self.settings.local_payload.read_text(encoding="utf-8"))
            snapshot_id = self.settings.snapshot_id or str(payload.get("snapshotId") or payload.get("snapshot_id") or "local")
            return blueprint_from_payload(payload, self.settings.hostname, snapshot_id, self.settings.boundary_pattern)

        snapshot_id = self.settings.snapshot_id
        if not snapshot_id:
            snapshots_payload = self.get_payload(self.snapshots_url())
            snapshot_id = latest_successful_snapshot_id(snapshots_payload)
            if not snapshot_id:
                raise MapperError(ExitCode.SNAPSHOT_NOT_FOUND, "No successfully completed snapshot was found.")

        devices_payload = self.get_payload_from_candidates(self.devices_urls(snapshot_id), "devices")
        topology_payload = self.get_payload_from_candidates(self.topology_urls(snapshot_id), "topology")
        command_outputs = self.get_command_outputs(snapshot_id)
        merged_payload = merge_payloads(devices_payload, topology_payload, command_outputs)
        return blueprint_from_payload(merged_payload, self.settings.hostname, snapshot_id, self.settings.boundary_pattern)

    def get_command_outputs(self, snapshot_id: str) -> dict[str, str]:
        outputs: dict[str, str] = {}
        for protocol, url in self.command_file_urls(snapshot_id):
            try:
                payload = self.get_payload(url)
            except MapperError as exc:
                if exc.exit_code == ExitCode.REQUEST_FAILED and exc.status_code == 404:
                    logging.warning("%s_file_not_found %s", protocol, json.dumps({"url": url}))
                    continue
                raise
            text = command_text_from_payload(payload)
            if text:
                outputs[protocol] = text
        return outputs


def merge_payloads(devices_payload: Any, topology_payload: Any, command_outputs: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "devices": collection_or_payload(devices_payload, "devices"),
        "links": collection_or_payload(topology_payload, "links"),
        "commandOutputs": command_outputs or {},
    }


def collection_or_payload(payload: Any, preferred_key: str) -> Any:
    if isinstance(payload, dict):
        for key in (preferred_key, "items", "data", "nodes", "edges", "connections", "adjacencies", "neighbors"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return payload


def blueprint_from_payload(payload: Any, hostname: str, snapshot_id: str, boundary_pattern: str) -> TopologyBlueprint:
    device = find_device_by_hostname(payload, hostname)
    if not device:
        raise MapperError(ExitCode.DEVICE_NOT_FOUND, f"Hostname '{hostname}' was not found in the topology payload.")
    neighbors = extract_neighbors(payload, hostname, boundary_pattern)
    if not neighbors:
        logging.warning("topology_neighbors_not_found %s", json.dumps({"hostname": hostname, "snapshot_id": snapshot_id}))
    return TopologyBlueprint(
        target=device_metadata(device, hostname),
        snapshot_id=snapshot_id,
        boundary_pattern=boundary_pattern,
        neighbors=tuple(neighbors),
    )
