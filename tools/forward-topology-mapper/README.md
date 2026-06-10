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

## Outputs

- Markdown blueprint with complete neighbor table.
- Large screen-view SVG with upstream boundaries above the switch and downstream neighbors in a grid.

See:

- `docs/example-topology-blueprint.md`
- `docs/example-network-map.svg`
