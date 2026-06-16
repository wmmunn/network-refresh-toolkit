from pathlib import Path
import unittest

from forward_config_downloader.client import ForwardClient
from forward_config_downloader.models import AuthSettings, DownloaderSettings


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.auth = None
        self.urls = []

    def get(self, url, timeout):
        self.urls.append((url, timeout))
        if url.endswith("/snapshots"):
            return FakeResponse({"items": [{"id": "snap-1", "status": "COMPLETED", "createdAt": "2026-06-01"}]})
        return FakeResponse({"devices": [{"name": "SW1", "config": {"rawText": "hostname SW1\n!"}}]})


class ClientTests(unittest.TestCase):
    def test_client_download_writes_config(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id=None,
                hostname="SW1",
                location_id=None,
                config_file=None,
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/config",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=200,
                max_line_pages=500,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = FakeSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(result.snapshot_id, "snap-1")
            self.assertEqual(result.output_path.read_text(encoding="utf-8"), "hostname SW1\n!\n")
            self.assertEqual(session.urls[0][0], "https://fwd.example/api/networks/network-1/snapshots")
            self.assertEqual(session.urls[1][0], "https://fwd.example/api/networks/network-1/snapshots/snap-1/devices")
            self.assertEqual(session.headers["Authorization"], "Bearer token-value")

    def test_client_tries_next_device_endpoint_after_404(self):
        import tempfile
        from requests.exceptions import RequestException

        class NotFoundError(RequestException):
            def __init__(self):
                response = type("Response", (), {"status_code": 404})()
                super().__init__("404 Client Error: Not Found", response=response)

        class FallbackResponse(FakeResponse):
            def __init__(self, payload, status_code=200):
                super().__init__(payload)
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code == 404:
                    raise NotFoundError()

        class FallbackSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/snapshots"):
                    return FallbackResponse({"items": [{"id": "snap-1", "status": "COMPLETED", "createdAt": "2026-06-01"}]})
                if "/bad-devices" in url:
                    return FallbackResponse({}, status_code=404)
                return FallbackResponse({"devices": [{"name": "SW1", "config": {"rawText": "hostname SW1\n!"}}]})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id=None,
                hostname="SW1",
                location_id=None,
                config_file=None,
                devices_path_templates=(
                    "/networks/{network_id}/snapshots/{snapshot_id}/bad-devices",
                    "/snapshots/{snapshot_id}/devices",
                ),
                config_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/config",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=200,
                max_line_pages=500,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = FallbackSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(result.snapshot_id, "snap-1")
            self.assertEqual(session.urls[1][0], "https://fwd.example/api/networks/network-1/snapshots/snap-1/bad-devices")
            self.assertEqual(session.urls[2][0], "https://fwd.example/api/snapshots/snap-1/devices")

    def test_client_uses_config_endpoint_when_device_payload_is_metadata_only(self):
        import tempfile

        class ConfigResponse(FakeResponse):
            text = ""

        class ConfigSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/snapshots"):
                    return ConfigResponse({"items": [{"id": "snap-1", "status": "COMPLETED", "createdAt": "2026-06-01"}]})
                if url.endswith("/devices"):
                    return ConfigResponse({"devices": [{"name": "SW1", "model": "switch-model"}]})
                return ConfigResponse({"rawText": "hostname SW1\n!"})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id=None,
                hostname="SW1",
                location_id=None,
                config_file=None,
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/config",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=200,
                max_line_pages=500,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = ConfigSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(result.output_path.read_text(encoding="utf-8"), "hostname SW1\n!\n")
            self.assertEqual(session.urls[2][0], "https://fwd.example/api/networks/network-1/snapshots/snap-1/devices/SW1/config")

    def test_client_can_use_location_file_config_endpoint(self):
        import tempfile

        class ConfigResponse(FakeResponse):
            text = ""

        class FileSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/devices"):
                    return ConfigResponse({"devices": [{"name": "SW1", "model": "switch-model"}]})
                return ConfigResponse({"rawText": "hostname SW1\n!"})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id="snap-1",
                hostname="SW1",
                location_id="82",
                config_file="SW1,configuration.txt",
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/files?locationId={location_id}&file={config_file}",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=200,
                max_line_pages=500,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = FileSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(result.output_path.read_text(encoding="utf-8"), "hostname SW1\n!\n")
            self.assertEqual(
                session.urls[1][0],
                "https://fwd.example/api/networks/network-1/snapshots/snap-1/files?locationId=82&file=SW1%2Cconfiguration.txt",
            )

    def test_client_skips_config_endpoint_that_returns_inventory_list(self):
        import tempfile

        class ConfigResponse(FakeResponse):
            text = ""

        class InventoryThenConfigSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/devices"):
                    return ConfigResponse({"devices": [{"name": "SW1", "model": "switch-model"}]})
                if "files?locationId=82" in url:
                    return ConfigResponse(["SW1,metadata.txt", "SW1,configuration.txt", "SW2,configuration.txt"])
                return ConfigResponse({"rawText": "hostname SW1\n!"})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id="snap-1",
                hostname="SW1",
                location_id="82",
                config_file="SW1,configuration.txt",
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=(
                    "/networks/{network_id}/snapshots/{snapshot_id}/files?locationId={location_id}&file={config_file}",
                    "/networks/{network_id}/snapshots/{snapshot_id}/devices/{device_name}/config",
                ),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=200,
                max_line_pages=500,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = InventoryThenConfigSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(result.output_path.read_text(encoding="utf-8"), "hostname SW1\n!\n")
            self.assertEqual(
                session.urls[1][0],
                "https://fwd.example/api/networks/network-1/snapshots/snap-1/files?locationId=82&file=SW1%2Cconfiguration.txt",
            )
            self.assertEqual(
                session.urls[2][0],
                "https://fwd.example/api/networks/network-1/snapshots/snap-1/devices/SW1/config",
            )

    def test_client_downloads_paged_config_file(self):
        import tempfile

        class ConfigResponse(FakeResponse):
            text = ""

        class PagedConfigSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/devices"):
                    return ConfigResponse({"devices": [{"name": "SW1", "model": "switch-model"}]})
                if "lines=0-2" in url:
                    return ConfigResponse(["version 17.9", "!", "hostname SW1"])
                if "lines=3-5" in url:
                    return ConfigResponse(["!", "interface GigabitEthernet1/0/1"])
                return ConfigResponse([])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id="snap-1",
                hostname="SW1",
                location_id=None,
                config_file="SW1,configuration.txt",
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=("/snapshots/{snapshot_id}/files/{config_file}?lines={line_start}-{line_end}",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=3,
                max_line_pages=10,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = PagedConfigSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(
                result.output_path.read_text(encoding="utf-8"),
                "version 17.9\n!\nhostname SW1\n!\ninterface GigabitEthernet1/0/1\n",
            )
            self.assertEqual(
                session.urls[1][0],
                "https://fwd.example/api/snapshots/snap-1/files/SW1,configuration.txt?lines=0-2",
            )
            self.assertEqual(
                session.urls[2][0],
                "https://fwd.example/api/snapshots/snap-1/files/SW1,configuration.txt?lines=3-5",
            )

    def test_client_downloads_paged_config_file_excerpts_shape(self):
        import tempfile

        class ConfigResponse(FakeResponse):
            text = ""

        class PagedExcerptSession(FakeSession):
            def get(self, url, timeout):
                self.urls.append((url, timeout))
                if url.endswith("/devices"):
                    return ConfigResponse({"devices": [{"name": "SW1", "model": "switch-model"}]})
                if "lines=0-2" in url:
                    return ConfigResponse(
                        {
                            "lineCount": 5,
                            "excerpts": [
                                {
                                    "start": 0,
                                    "end": 2,
                                    "lines": ["version 17.9", "!", "hostname SW1"],
                                }
                            ],
                        }
                    )
                if "lines=3-5" in url:
                    return ConfigResponse(
                        {
                            "lineCount": 5,
                            "excerpts": [
                                {
                                    "start": 3,
                                    "end": 4,
                                    "lines": ["!", "interface GigabitEthernet1/0/1"],
                                }
                            ],
                        }
                    )
                return ConfigResponse({"lineCount": 5, "excerpts": []})

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = DownloaderSettings(
                base_url="https://fwd.example",
                api_prefix="/api",
                network_id="network-1",
                snapshot_id="snap-1",
                hostname="SW1",
                location_id=None,
                config_file="SW1,configuration.txt",
                devices_path_templates=("/networks/{network_id}/snapshots/{snapshot_id}/devices",),
                config_path_templates=("/snapshots/{snapshot_id}/files/{config_file}?lines={line_start}-{line_end}",),
                output_dir=temp_path / "manifests",
                logs_dir=temp_path / "logs",
                timeout_seconds=5.0,
                line_page_size=3,
                max_line_pages=10,
                auth=AuthSettings(mode="bearer", token="token-value"),
            )
            session = PagedExcerptSession()

            result = ForwardClient(settings, session=session).download()

            self.assertEqual(
                result.output_path.read_text(encoding="utf-8"),
                "version 17.9\n!\nhostname SW1\n!\ninterface GigabitEthernet1/0/1\n",
            )


if __name__ == "__main__":
    unittest.main()
