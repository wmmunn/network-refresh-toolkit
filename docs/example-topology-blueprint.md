# Forward Networks Topology Blueprint: ACCESS-SW01

## Source

- Snapshot ID: `sanitized-snapshot-1`
- Generated: `2026-06-17 15:56:56`
- Scope: target switch plus active one-hop Forward topology/CDP/LLDP neighbors only.
- Traversal boundary: neighbors matching `(dist|distribution|core|router|rtr|gw|gateway)` are included but not expanded.

## Target Switch

| Field | Value |
| --- | --- |
| Hostname | `ACCESS-SW01` |
| Primary IP | `192.0.2.10` |
| Device type | `Catalyst Access Switch` |
| Location / IDF / closet | `IDF-A` |

## Active Topology Neighbors

| Local interface | Protocol | Neighbor | Neighbor IP | Remote port | Boundary |
| --- | --- | --- | --- | --- | --- |
| `TenGigabitEthernet1/1/1` | LLDP | `CORE-RTR01` | `Unknown` | `TenGigabitEthernet0/0/1` | Yes |
| `TenGigabitEthernet1/1/2` | LLDP | `CORE-RTR02` | `Unknown` | `TenGigabitEthernet0/0/1` | Yes |
| `GigabitEthernet1/0/12` | CDP | `AP-01` | `Unknown` | `eth0` | No |

## Network Map

![Network map](ACCESS-SW01__snapshot-sanitized-snapshot-1__network-map.svg)
