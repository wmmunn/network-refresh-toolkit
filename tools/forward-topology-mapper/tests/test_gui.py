from pathlib import Path
import unittest

from forward_topology_mapper.gui import build_settings_from_values, bundled_icon_path, bundled_sample_payload_path


class GuiSettingsTests(unittest.TestCase):
    def test_builds_settings_for_local_payload(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "sanitized-topology.json"
        settings = build_settings_from_values(
            {
                "hostname": "ACCESS-SW01",
                "network_id": "",
                "snapshot_id": "",
                "local_payload": str(fixture),
                "output_dir": "out",
                "logs_dir": "logs",
                "timeout_seconds": "15",
                "auth_mode": "basic",
                "api_token": "",
                "base_url": "https://fwd.app",
                "api_prefix": "/api",
                "boundary_pattern": "",
            }
        )

        self.assertEqual(settings.hostname, "ACCESS-SW01")
        self.assertEqual(settings.local_payload, fixture)
        self.assertEqual(settings.timeout_seconds, 15.0)
        self.assertEqual(settings.auth.mode, "basic")

    def test_sample_payload_path_exists_from_source(self):
        self.assertTrue(bundled_sample_payload_path().exists())

    def test_icon_path_exists_from_source(self):
        self.assertTrue(bundled_icon_path().exists())

    def test_offline_payload_is_ignored_until_enabled(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "sanitized-topology.json"
        settings = build_settings_from_values(
            {
                "hostname": "ACCESS-SW01",
                "network_id": "NETWORK_ID",
                "snapshot_id": "",
                "use_offline": "0",
                "local_payload": str(fixture),
                "output_dir": "out",
                "logs_dir": "logs",
                "timeout_seconds": "15",
                "auth_mode": "basic",
                "api_token": "",
                "base_url": "https://fwd.app",
                "api_prefix": "/api",
                "boundary_pattern": "",
            }
        )

        self.assertIsNone(settings.local_payload)


if __name__ == "__main__":
    unittest.main()
