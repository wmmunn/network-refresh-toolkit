from pathlib import Path
import tempfile
import unittest

from forward_topology_mapper.cli import build_parser, main, settings_from_args


class CliTests(unittest.TestCase):
    def test_settings_default_network_id_is_empty_string(self):
        parser = build_parser()
        args = parser.parse_args(["--hostname", "ACCESS-SW01"])

        settings = settings_from_args(args)

        self.assertEqual(settings.network_id, "")

    def test_cli_can_render_from_local_payload(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "sanitized-topology.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main([
                "--hostname",
                "ACCESS-SW01",
                "--local-payload",
                str(fixture),
                "--output-dir",
                temp_dir,
                "--logs-dir",
                str(Path(temp_dir) / "logs"),
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(temp_dir) / "ACCESS-SW01__snapshot-sanitized-snapshot-1__topology-blueprint.md").exists())
            self.assertTrue((Path(temp_dir) / "ACCESS-SW01__snapshot-sanitized-snapshot-1__network-map.svg").exists())


if __name__ == "__main__":
    unittest.main()