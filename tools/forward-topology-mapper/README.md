# Forward Topology Mapper

Sanitized portfolio summary of a read-only topology mapping tool for switch refresh documentation.

## Goal

Given a target access switch hostname, create a practical diagram and lookup sheet showing:

- the target switch
- switch management IP and device type
- upstream gateway/router boundary pair
- direct one-hop CDP/LLDP neighbors below the switch
- local interface and remote port details
- neighbor management IPs when available

## Workflow

```text
1. Read API credentials from environment variables.
2. Select a network snapshot.
3. Fetch device metadata.
4. Fetch modeled topology links.
5. Fetch per-switch CDP/LLDP snapshot files.
6. Normalize neighbor records.
7. Mark upstream gateway/router devices as traversal boundaries.
8. Write Markdown and SVG artifacts for operator review.
```

## Safety Model

- Read-only API calls.
- No device-side commands.
- No credentials in examples or output files.
- No traversal beyond the first upstream boundary pair.
- Output is designed for review, not execution.

## Environment And Tenant Setup

Before running a topology mapper against a real Forward Networks environment, obtain and confirm:

- Your Forward Networks tenant/base URL.
- Your network or tenant-scoped network ID.
- The authentication method approved for your tenant.
- Whether your tenant uses the default API prefix, such as `/api`.
- The endpoint structure for snapshots, devices, modeled topology links, and snapshot file content.
- The naming and location pattern for CDP/LLDP snapshot files.

Expected environment variables for a typical implementation:

```powershell
$env:FORWARD_NETWORKS_KEY = "your-key"
$env:FORWARD_NETWORKS_SECRET = "your-secret"
$env:FORWARD_NETWORKS_NETWORK_ID = "your-network-id"
```

Optional environment variables may include:

```powershell
$env:FWD_BASE_URL = "https://your-forward-tenant.example"
$env:FWD_API_PREFIX = "/api"
```

Forward Networks deployments can differ by tenant, API version, and enabled features. Treat endpoint paths and file names as tenant-specific details that must be confirmed before use.

## Tenant Discovery Notes

The mapper depends on more than one Forward data shape:

1. Snapshot discovery.
2. Device metadata lookup.
3. Modeled topology link retrieval.
4. File-content retrieval for CDP and LLDP command outputs.
5. Device/name matching across those payloads.

In practice, adapting the mapper may require a few controlled endpoint attempts to confirm where a tenant exposes each data set. Review local logs and sanitized payload-shape notes while tuning endpoint templates. Do not publish raw tenant payloads, hostnames, IPs, or logs.

## Outputs

- Markdown blueprint with complete neighbor table.
- Large screen-view SVG with upstream boundaries above the switch and downstream neighbors in a grid.

See:

- `docs/example-topology-blueprint.md`
- `docs/example-network-map.svg`
