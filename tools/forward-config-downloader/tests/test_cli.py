import logging
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from forward_config_downloader.cli import main, settings_from_args
from forward_config_downloader.models import ExitCode


class CliTests(TestCase):
    def test_settings_reads_forward_networks_credentials_from_environment(self):
        parser_args = type(
            "Args",
            (),
            {
                "auth_mode": "basic",
                "api_token": None,
                "base_url": "https://fwd.example",
                "api_prefix": "/api",
                "network_id": "network-1",
                "snapshot_id": None,
                "hostname": "SW1",
                "location_id": None,
                "config_file": None,
                "devices_path_template": None,
                "config_path_template": None,
                "output_dir": Path("manifests"),
                "logs_dir": Path("logs"),
                "timeout_seconds": 5.0,
                "line_page_size": 200,
                "max_line_pages": 500,
            },
        )()

        with patch.dict(
            "os.environ",
            {
                "FORWARD_NETWORKS_KEY": "key-value",
                "FORWARD_NETWORKS_SECRET": "secret-value",
            },
            clear=False,
        ):
            settings = settings_from_args(parser_args)

        self.assertEqual(settings.auth.key, "key-value")
        self.assertEqual(settings.auth.secret, "secret-value")
        self.assertEqual(settings.network_id, "network-1")

    def test_settings_can_read_network_id_from_environment(self):
        parser_args = type(
            "Args",
            (),
            {
                "auth_mode": "basic",
                "api_token": None,
                "base_url": "https://fwd.example",
                "api_prefix": "/api",
                "network_id": "env-network",
                "snapshot_id": None,
                "hostname": "SW1",
                "location_id": None,
                "config_file": None,
                "devices_path_template": None,
                "config_path_template": None,
                "output_dir": Path("manifests"),
                "logs_dir": Path("logs"),
                "timeout_seconds": 5.0,
                "line_page_size": 200,
                "max_line_pages": 500,
            },
        )()

        settings = settings_from_args(parser_args)

        self.assertEqual(settings.network_id, "env-network")

    def test_settings_default_network_id_is_blank_in_public_sample(self):
        parser_args = type(
            "Args",
            (),
            {
                "auth_mode": "basic",
                "api_token": None,
                "base_url": "https://fwd.example",
                "api_prefix": "/api",
                "network_id": "",
                "snapshot_id": None,
                "hostname": "SW1",
                "location_id": None,
                "config_file": None,
                "devices_path_template": None,
                "config_path_template": None,
                "output_dir": Path("manifests"),
                "logs_dir": Path("logs"),
                "timeout_seconds": 5.0,
                "line_page_size": 200,
                "max_line_pages": 500,
            },
        )()

        settings = settings_from_args(parser_args)

        self.assertEqual(settings.network_id, "")

    def test_missing_forward_networks_credentials_logs_and_exits_one(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "logs"
            with patch.dict("os.environ", {}, clear=True):
                exit_code = main(
                    [
                        "--network-id",
                        "network-1",
                        "--hostname",
                        "SW1",
                        "--logs-dir",
                        str(logs_dir),
                    ]
                )

            logging.shutdown()
            log_files = list(logs_dir.glob("forward-config-downloader-*.log"))
            log_text = log_files[0].read_text(encoding="utf-8") if log_files else ""
            for handler in logging.getLogger().handlers[:]:
                logging.getLogger().removeHandler(handler)
                handler.close()

            self.assertEqual(exit_code, int(ExitCode.CONFIG_ERROR))
            self.assertEqual(exit_code, 1)
            self.assertEqual(len(log_files), 1)
            self.assertIn("FORWARD_NETWORKS_KEY", log_text)
