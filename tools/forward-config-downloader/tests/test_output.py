import json
import logging
import tempfile
import unittest
from pathlib import Path

from forward_config_downloader.output import configure_logging, log_event, sanitize_for_log


class OutputSafetyTests(unittest.TestCase):
    def test_sanitize_for_log_redacts_sensitive_mapping_values(self):
        safe = sanitize_for_log(
            {
                "api_token": "token-value",
                "nested": {"FORWARD_NETWORKS_SECRET": "secret-value"},
                "urls": ["https://fwd.example/api/path?token=abc&file=SW1,configuration.txt"],
            }
        )

        self.assertEqual(safe["api_token"], "<redacted>")
        self.assertEqual(safe["nested"]["FORWARD_NETWORKS_SECRET"], "<redacted>")
        self.assertIn("token=%3Credacted%3E", safe["urls"][0])
        self.assertIn("file=SW1%2Cconfiguration.txt", safe["urls"][0])

    def test_log_event_redacts_sensitive_values_written_to_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = configure_logging(Path(temp_dir))
            log_event(
                logging.ERROR,
                "download_failed",
                error="Authorization: Bearer token-value; secret=secret-value",
                api_token="token-value",
            )
            logging.shutdown()
            for handler in logging.getLogger().handlers[:]:
                logging.getLogger().removeHandler(handler)
                handler.close()

            log_text = log_path.read_text(encoding="utf-8")
            payload = log_text.split("download_failed ", 1)[1]
            fields = json.loads(payload)

            self.assertEqual(fields["api_token"], "<redacted>")
            self.assertIn("Bearer <redacted>", fields["error"])
            self.assertIn("secret=<redacted>", fields["error"])
            self.assertNotIn("token-value", log_text)
            self.assertNotIn("secret-value", log_text)


if __name__ == "__main__":
    unittest.main()
