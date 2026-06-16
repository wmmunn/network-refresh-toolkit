import unittest

from forward_config_downloader.payloads import (
    extract_running_config,
    find_device_by_hostname,
    latest_successful_snapshot_id,
    payload_shape,
)


class PayloadTests(unittest.TestCase):
    def test_latest_successful_snapshot_id_uses_newest_completed_snapshot(self):
        payload = {
            "items": [
                {"id": "old-good", "status": "COMPLETED", "createdAt": "2026-05-01T12:00:00Z"},
                {"id": "new-running", "status": "RUNNING", "createdAt": "2026-06-01T12:00:00Z"},
                {"id": "new-good", "status": "SUCCEEDED", "createdAt": "2026-06-02T12:00:00Z"},
            ]
        }

        self.assertEqual(latest_successful_snapshot_id(payload), "new-good")

    def test_find_device_by_hostname_accepts_wrapped_devices_payload(self):
        payload = {
            "devices": [
                {"name": "SW-ACCESS-01", "config": {"rawText": "hostname SW-ACCESS-01"}},
                {"hostname": "SW-ACCESS-02", "config": {"rawText": "hostname SW-ACCESS-02"}},
            ]
        }

        self.assertEqual(find_device_by_hostname(payload, "sw-access-02"), payload["devices"][1])

    def test_extract_running_config_prefers_config_raw_text(self):
        device = {"name": "SW-ACCESS-01", "config": {"rawText": "hostname SW-ACCESS-01\r\n!"}}

        self.assertEqual(extract_running_config(device), "hostname SW-ACCESS-01\n!\n")

    def test_extract_running_config_can_use_command_output_fallback(self):
        device = {
            "name": "SW-ACCESS-01",
            "commandOutputs": [
                {"command": "show version", "output": "version text"},
                {"command": "show running-config", "output": "hostname SW-ACCESS-01\n!"},
            ],
        }

        self.assertEqual(extract_running_config(device), "hostname SW-ACCESS-01\n!\n")

    def test_extract_running_config_can_use_nested_command_output_mapping(self):
        device = {
            "name": "SW-ACCESS-01",
            "outputs": {
                "show running-config": {
                    "response": {
                        "text": "hostname SW-ACCESS-01\n!",
                    }
                }
            },
        }

        self.assertEqual(extract_running_config(device), "hostname SW-ACCESS-01\n!\n")

    def test_extract_running_config_can_use_nested_config_text_key(self):
        device = {
            "name": "SW-ACCESS-01",
            "details": {
                "files": [
                    {
                        "fileName": "running-config",
                        "rawText": "hostname SW-ACCESS-01\n!",
                    }
                ]
            },
        }

        self.assertEqual(extract_running_config(device), "hostname SW-ACCESS-01\n!\n")

    def test_extract_running_config_can_use_line_list_payload(self):
        payload = [
            "version 17.9",
            "!",
            "hostname SW-ACCESS-01",
            "!",
            "interface GigabitEthernet1/0/1",
            " description ACCESS",
        ]

        self.assertEqual(
            extract_running_config(payload),
            "version 17.9\n!\nhostname SW-ACCESS-01\n!\ninterface GigabitEthernet1/0/1\n description ACCESS\n",
        )

    def test_extract_running_config_rejects_string_list_inventory(self):
        payload = [
            "SW-ACCESS-01",
            "SW-ACCESS-02",
            "SW-ACCESS-03",
        ]

        self.assertIsNone(extract_running_config(payload))

    def test_payload_shape_does_not_include_values(self):
        shape = payload_shape({"name": "SW1", "config": {"rawText": "hostname SW1\n!"}})

        self.assertEqual(shape, {"config": {"rawText": "str"}, "name": "str"})


if __name__ == "__main__":
    unittest.main()
