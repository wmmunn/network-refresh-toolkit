import unittest

from forward_topology_mapper.payloads import device_metadata, extract_neighbors, find_device_by_hostname


class PayloadTests(unittest.TestCase):
    def test_extracts_metadata_from_nested_variables(self):
        payload = {
            "devices": [
                {
                    "name": "ACCESS-SW01",
                    "primaryIp": "192.0.2.10",
                    "deviceType": "Catalyst Access Switch",
                    "customVariables": {"idf": "IDF-A"},
                }
            ]
        }

        device = find_device_by_hostname(payload, "access-sw01")
        metadata = device_metadata(device, "access-sw01")

        self.assertEqual(metadata.hostname, "ACCESS-SW01")
        self.assertEqual(metadata.ip_address, "192.0.2.10")
        self.assertEqual(metadata.device_type, "Catalyst Access Switch")
        self.assertEqual(metadata.location, "IDF-A")

    def test_extracts_management_ip_from_forward_list_field(self):
        payload = {
            "devices": [
                {
                    "name": "ACCESS-SW01",
                    "managementIps": ["192.0.2.10"],
                    "type": "SWITCH",
                }
            ]
        }

        device = find_device_by_hostname(payload, "ACCESS-SW01")
        metadata = device_metadata(device, "ACCESS-SW01")

        self.assertEqual(metadata.ip_address, "192.0.2.10")

    def test_extracts_active_inline_cdp_lldp_neighbors_and_marks_boundary(self):
        payload = {
            "devices": [
                {
                    "name": "ACCESS-SW01",
                    "lldpNeighbors": [
                        {
                            "protocol": "LLDP",
                            "localInterface": "Te1/1/1",
                            "neighborHostname": "CORE-RTR01",
                            "remotePort": "Te0/0/1",
                            "deviceType": "core router",
                            "active": True,
                        },
                        {
                            "protocol": "LLDP",
                            "localInterface": "Gi1/0/1",
                            "neighborHostname": "OLD-DEVICE",
                            "remotePort": "eth0",
                            "state": "stale",
                        },
                        {
                            "protocol": "ISIS",
                            "localInterface": "Gi1/0/2",
                            "neighborHostname": "IGNORED",
                            "remotePort": "eth0",
                        },
                    ],
                    "cdpNeighbors": [
                        {
                            "protocol": "CDP",
                            "localInterface": "Gi1/0/12",
                            "neighborHostname": "AP-01",
                            "remotePort": "eth0",
                        }
                    ],
                }
            ]
        }

        neighbors = extract_neighbors(payload, "ACCESS-SW01", r"(core|router|rtr)")

        self.assertEqual(len(neighbors), 2)
        self.assertTrue(neighbors[0].is_boundary)
        self.assertEqual(neighbors[0].neighbor_hostname, "CORE-RTR01")
        self.assertEqual(neighbors[1].neighbor_hostname, "AP-01")

    def test_extracts_graph_style_link_neighbors(self):
        payload = {
            "devices": [{"name": "ACCESS-SW01"}],
            "links": [
                {
                    "protocol": "LLDP",
                    "sourceDevice": "ACCESS-SW01",
                    "targetDevice": "DIST-RTR01",
                    "sourceInterface": "Te1/1/1",
                    "targetInterface": "Te0/0/1",
                }
            ],
        }

        neighbors = extract_neighbors(payload, "ACCESS-SW01", r"(dist|router|rtr)")

        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].local_interface, "Te1/1/1")
        self.assertEqual(neighbors[0].remote_port, "Te0/0/1")
        self.assertTrue(neighbors[0].is_boundary)

    def test_extracts_forward_source_port_target_port_links(self):
        payload = {
            "devices": [
                {"name": "ACCESS-SW01"},
                {"name": "CORE-RTR01", "managementIps": ["192.0.2.1"]},
            ],
            "links": [
                {
                    "sourcePort": "ACCESS-SW01 te1/1/1",
                    "targetPort": "CORE-RTR01 twe1/0/22",
                },
                {
                    "sourcePort": "CORE-RTR01 twe1/0/22",
                    "targetPort": "ACCESS-SW01 te1/1/1",
                },
            ],
        }

        neighbors = extract_neighbors(payload, "ACCESS-SW01", r"(core|router|rtr)")

        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].local_interface, "te1/1/1")
        self.assertEqual(neighbors[0].neighbor_hostname, "CORE-RTR01")
        self.assertEqual(neighbors[0].remote_port, "twe1/0/22")
        self.assertEqual(neighbors[0].neighbor_ip, "192.0.2.1")
        self.assertEqual(neighbors[0].protocol, "TOPOLOGY")
        self.assertTrue(neighbors[0].is_boundary)

    def test_extracts_lldp_detail_file_neighbors(self):
        payload = {
            "devices": [{"name": "ACCESS-SW01"}],
            "commandOutputs": {
                "lldp": """
show lldp neighbors detail
------------------------------------------------
Local Intf: Te1/0/3
Port id: eth0
System Name: AP-01
System Capabilities: W
Management Addresses:
    IP: 192.0.2.31
------------------------------------------------
Local Intf: Te1/1/1
Port id: Twe1/0/22
System Name: CORE-RTR01.example.test
System Capabilities: B,R
Management Addresses:
    IP: 192.0.2.1
""",
            },
        }

        neighbors = extract_neighbors(payload, "ACCESS-SW01", r"(core|router|rtr|gw)")

        self.assertEqual(len(neighbors), 2)
        self.assertEqual(neighbors[0].neighbor_hostname, "CORE-RTR01.example.test")
        self.assertEqual(neighbors[0].neighbor_ip, "192.0.2.1")
        self.assertTrue(neighbors[0].is_boundary)
        self.assertEqual(neighbors[1].neighbor_hostname, "AP-01")
        self.assertEqual(neighbors[1].neighbor_ip, "192.0.2.31")

    def test_extracts_cdp_detail_file_neighbors_and_dedupes_topology(self):
        payload = {
            "devices": [{"name": "ACCESS-SW01"}],
            "links": [
                {
                    "sourcePort": "ACCESS-SW01 te1/1/1",
                    "targetPort": "CORE-RTR01 twe1/0/22",
                },
            ],
            "commandOutputs": {
                "cdp": """
-------------------------
Device ID: CORE-RTR01.example.test
Entry address(es):
  IP address: 192.0.2.1
Platform: cisco C9500,  Capabilities: Router Switch IGMP
Interface: TenGigabitEthernet1/1/1,  Port ID (outgoing port): TwentyFiveGigE1/0/22
Holdtime : 144 sec
""",
            },
        }

        neighbors = extract_neighbors(payload, "ACCESS-SW01", r"(core|router|rtr|gw)")

        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].protocol, "CDP")
        self.assertEqual(neighbors[0].neighbor_hostname, "CORE-RTR01.example.test")
        self.assertEqual(neighbors[0].neighbor_ip, "192.0.2.1")


if __name__ == "__main__":
    unittest.main()
