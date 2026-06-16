from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

try:
    import requests
    from requests import Session
    from requests.auth import HTTPBasicAuth
    from requests.exceptions import RequestException
except ImportError:  # pragma: no cover - covered by CLI configuration handling.
    requests = None
    Session = Any
    HTTPBasicAuth = None
    RequestException = Exception

from .models import AuthSettings, DownloaderSettings, DownloadResult, ExitCode
from .output import log_event, write_config
from .payloads import (
    device_hostname,
    extract_running_config,
    find_device_by_hostname,
    latest_successful_snapshot_id,
    payload_shape,
)


class DownloaderError(Exception):
    def __init__(self, exit_code: ExitCode, message: str, status_code: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.status_code = status_code


class ForwardClient:
    def __init__(self, settings: DownloaderSettings, session: Session | None = None):
        if requests is None and session is None:
            raise DownloaderError(
                ExitCode.CONFIG_ERROR,
                "The 'requests' library is required. Install it before running this tool.",
            )

        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._apply_auth(settings.auth)

    def _apply_auth(self, auth: AuthSettings) -> None:
        if auth.mode == "bearer":
            if not auth.token:
                raise DownloaderError(ExitCode.CONFIG_ERROR, "Bearer auth requires FWD_API_TOKEN or --api-token.")
            self.session.headers.update({"Authorization": f"Bearer {auth.token}"})
            return

        if not auth.key or not auth.secret:
            raise DownloaderError(
                ExitCode.CONFIG_ERROR,
                "Basic auth requires FWD_API_KEY/FWD_API_SECRET or --api-key/--api-secret.",
            )
        self.session.auth = HTTPBasicAuth(auth.key, auth.secret) if HTTPBasicAuth else (auth.key, auth.secret)

    def snapshots_url(self) -> str:
        return self._url("/networks/{network_id}/snapshots")

    def devices_url(self, snapshot_id: str) -> str:
        return self.devices_urls(snapshot_id)[0]

    def devices_urls(self, snapshot_id: str) -> list[str]:
        return [self._url(template, snapshot_id=snapshot_id) for template in self.settings.devices_path_templates]

    def config_urls(self, snapshot_id: str, device: dict) -> list[str]:
        device_name = device_hostname(device) or self.settings.hostname
        urls: list[str] = []
        for template in self.settings.config_path_templates:
            if "{line_start}" in template or "{line_end}" in template:
                urls.append(
                    self._url(
                        template,
                        snapshot_id=snapshot_id,
                        device_name=device_name,
                        location_id=self.settings.location_id or "",
                        config_file=self.config_file_name(device_name),
                        line_start="0",
                        line_end=str(self.settings.line_page_size - 1),
                    )
                )
                continue
            if "{location_id}" in template and not self.settings.location_id:
                continue
            if "{config_file}" in template and not self.config_file_name(device_name):
                continue
            urls.append(
                self._url(
                    template,
                    snapshot_id=snapshot_id,
                    device_name=device_name,
                    location_id=self.settings.location_id or "",
                    config_file=self.config_file_name(device_name),
                )
            )
        return urls

    def paged_config_templates(self) -> list[str]:
        return [
            template
            for template in self.settings.config_path_templates
            if "{line_start}" in template or "{line_end}" in template
        ]

    def config_file_name(self, device_name: str) -> str:
        return self.settings.config_file or f"{device_name},configuration.txt"

    def _url(self, path_template: str, **values: str) -> str:
        quoted_values = {}
        for key, value in values.items():
            safe_chars = "," if key == "config_file" and "{config_file}?" in path_template else ""
            quoted_values[key] = quote(value, safe=safe_chars)

        quoted = {
            "network_id": quote(self.settings.network_id, safe=""),
            **quoted_values,
        }
        base_url = self.settings.base_url.rstrip("/")
        prefix = self.settings.api_prefix.strip("/")
        path = path_template.format(**quoted).lstrip("/")
        if prefix:
            return f"{base_url}/{prefix}/{path}"
        return f"{base_url}/{path}"

    def get_payload(self, url: str) -> Any:
        try:
            response = self.session.get(url, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                text = getattr(response, "text", "")
                if isinstance(text, str) and text.strip():
                    return text
                raise
        except RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            raise DownloaderError(ExitCode.REQUEST_FAILED, f"API request failed: {exc}", status_code=status_code) from exc
        except ValueError as exc:
            raise DownloaderError(ExitCode.REQUEST_FAILED, f"API response was not valid JSON or text: {exc}") from exc

    def get_json(self, url: str) -> Any:
        return self.get_payload(url)

    def get_payload_from_candidates(self, urls: list[str], event_prefix: str) -> Any:
        not_found: list[str] = []
        last_error: DownloaderError | None = None
        for url in urls:
            try:
                return self.get_payload(url)
            except DownloaderError as exc:
                last_error = exc
                if exc.exit_code == ExitCode.REQUEST_FAILED and exc.status_code == 404:
                    not_found.append(url)
                    log_event(logging.WARNING, f"{event_prefix}_endpoint_not_found", url=url)
                    continue
                raise

        tried = "; ".join(not_found)
        message = f"All candidate {event_prefix} endpoints returned 404. Tried: {tried}"
        raise DownloaderError(ExitCode.REQUEST_FAILED, message, status_code=404) from last_error

    def get_json_from_candidates(self, urls: list[str]) -> Any:
        return self.get_payload_from_candidates(urls, "devices")

    def get_running_config_from_candidates(self, urls: list[str], hostname: str, snapshot_id: str) -> str | None:
        not_found: list[str] = []
        last_error: DownloaderError | None = None
        for url in urls:
            try:
                payload = self.get_payload(url)
            except DownloaderError as exc:
                last_error = exc
                if exc.exit_code == ExitCode.REQUEST_FAILED and exc.status_code == 404:
                    not_found.append(url)
                    log_event(logging.WARNING, "config_endpoint_not_found", url=url)
                    continue
                raise

            config_text = extract_running_config(payload)
            if config_text:
                log_event(logging.INFO, "config_endpoint_selected", url=url)
                return config_text

            log_event(
                logging.WARNING,
                "config_endpoint_without_running_config",
                hostname=hostname,
                snapshot_id=snapshot_id,
                url=url,
                config_payload_shape=payload_shape(payload),
            )

        if not_found:
            log_event(logging.WARNING, "config_endpoints_not_found", urls=not_found)
        if last_error and len(not_found) == len(urls):
            tried = "; ".join(not_found)
            raise DownloaderError(
                ExitCode.REQUEST_FAILED,
                f"All candidate config endpoints returned 404. Tried: {tried}",
                status_code=404,
            ) from last_error
        return None

    def get_running_config_from_paged_templates(self, snapshot_id: str, device: dict) -> str | None:
        device_name = device_hostname(device) or self.settings.hostname
        for template in self.paged_config_templates():
            lines: list[str] = []
            selected_urls: list[str] = []
            for page_index in range(self.settings.max_line_pages):
                line_start = page_index * self.settings.line_page_size
                line_end = line_start + self.settings.line_page_size - 1
                url = self._url(
                    template,
                    snapshot_id=snapshot_id,
                    device_name=device_name,
                    location_id=self.settings.location_id or "",
                    config_file=self.config_file_name(device_name),
                    line_start=str(line_start),
                    line_end=str(line_end),
                )
                try:
                    payload = self.get_payload(url)
                except DownloaderError as exc:
                    if exc.exit_code == ExitCode.REQUEST_FAILED and exc.status_code == 404:
                        log_event(logging.WARNING, "paged_config_endpoint_not_found", url=url)
                        break
                    raise

                page_lines = string_list_payload(payload)
                if not page_lines:
                    if page_index == 0:
                        log_event(
                            logging.WARNING,
                            "paged_config_without_line_list",
                            url=url,
                            config_payload_shape=payload_shape(payload),
                        )
                    break

                lines.extend(page_lines)
                selected_urls.append(url)
                if len(page_lines) < self.settings.line_page_size:
                    break

            config_text = extract_running_config(lines)
            if config_text:
                log_event(
                    logging.INFO,
                    "paged_config_endpoint_selected",
                    first_url=selected_urls[0] if selected_urls else None,
                    pages=len(selected_urls),
                    lines=len(lines),
                )
                return config_text
        return None

    def download(self) -> DownloadResult:
        snapshot_id = self.settings.snapshot_id
        if snapshot_id:
            log_event(logging.INFO, "snapshot_selected", snapshot_id=snapshot_id, source="cli")
        else:
            log_event(logging.INFO, "snapshots_request", url=self.snapshots_url())
            snapshots_payload = self.get_json(self.snapshots_url())
            snapshot_id = latest_successful_snapshot_id(snapshots_payload)
            if not snapshot_id:
                raise DownloaderError(ExitCode.SNAPSHOT_NOT_FOUND, "No successfully completed snapshot was found.")

        devices_urls = self.devices_urls(snapshot_id)
        log_event(logging.INFO, "devices_request", urls=devices_urls, snapshot_id=snapshot_id)
        devices_payload = self.get_json_from_candidates(devices_urls)
        device = find_device_by_hostname(devices_payload, self.settings.hostname)
        if not device:
            raise DownloaderError(
                ExitCode.DEVICE_NOT_FOUND,
                f"Hostname '{self.settings.hostname}' was not found in snapshot '{snapshot_id}'.",
            )

        config_text = extract_running_config(device)
        if not config_text:
            config_urls = self.config_urls(snapshot_id, device)
            log_event(logging.INFO, "config_request", urls=config_urls, snapshot_id=snapshot_id)
            config_text = self.get_running_config_from_paged_templates(snapshot_id, device)
        if not config_text:
            config_text = self.get_running_config_from_candidates(
                [url for url in config_urls if "lines=0-" not in url],
                self.settings.hostname,
                snapshot_id,
            )

        if not config_text:
            log_event(
                logging.ERROR,
                "running_config_not_found",
                hostname=self.settings.hostname,
                snapshot_id=snapshot_id,
                device_payload_shape=payload_shape(device),
            )
            raise DownloaderError(
                ExitCode.CONFIG_NOT_FOUND,
                f"Hostname '{self.settings.hostname}' was found, but no running-config text was present.",
            )

        try:
            output_path = write_config(
                self.settings.output_dir,
                self.settings.hostname,
                snapshot_id,
                config_text,
            )
        except OSError as exc:
            raise DownloaderError(ExitCode.OUTPUT_FAILED, f"Could not write output file: {exc}") from exc

        log_event(
            logging.INFO,
            "config_written",
            hostname=self.settings.hostname,
            snapshot_id=snapshot_id,
            output_path=str(output_path),
        )
        return DownloadResult(
            hostname=self.settings.hostname,
            snapshot_id=snapshot_id,
            output_path=output_path,
        )


def string_list_payload(payload: Any) -> list[str]:
    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        return [line.rstrip("\r\n") for line in payload]
    if isinstance(payload, dict):
        excerpts = payload.get("excerpts")
        if isinstance(excerpts, list):
            lines: list[str] = []
            for excerpt in excerpts:
                if not isinstance(excerpt, dict):
                    continue
                excerpt_lines = excerpt.get("lines")
                if isinstance(excerpt_lines, list) and all(isinstance(item, str) for item in excerpt_lines):
                    lines.extend(line.rstrip("\r\n") for line in excerpt_lines)
            if lines:
                return lines

        for key in ("lines", "data", "items", "content"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return [line.rstrip("\r\n") for line in value]
    return []
