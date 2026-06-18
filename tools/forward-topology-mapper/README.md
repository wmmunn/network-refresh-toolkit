# Forward Topology Mapper

[![Snyk: Topology Mapper](https://snyk.io/test/github/wmmunn/network-refresh-toolkit/badge.svg?targetFile=tools%2Fforward-topology-mapper%2Frequirements.txt)](https://snyk.io/test/github/wmmunn/network-refresh-toolkit?targetFile=tools%2Fforward-topology-mapper%2Frequirements.txt)

Sanitized public source for a read-only topology mapping tool for switch refresh documentation.

Current public version: `v0.4.0`.

## Goal

Given a target access switch hostname, create a practical diagram and lookup sheet showing:

- the target switch
- switch management IP and device type
- upstream gateway/router boundary pair
- direct one-hop CDP/LLDP neighbors
- local interface and remote port details
- neighbor management IPs when available

## Interface

The recommended operator path is the Tkinter GUI:

```powershell
python .\forward_topology_mapper_gui.py
```

The GUI keeps the workflow read-only, shows credential readiness, supports a sanitized local payload for offline testing, and opens the generated Markdown/SVG outputs for review.

The CLI remains available for repeatable runs and tests:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m forward_topology_mapper.cli --help
```

## Source Included

This public version includes a runnable Python package under `src/`, a sanitized local payload and sample SVG under `examples/`, a GUI launcher, a CLI launcher, a PyInstaller spec, icon assets, and sanitized tests under `tests/`.

It intentionally does not include:

- private tenant IDs
- real hostnames or IP addresses
- raw Forward Networks payloads
- logs or generated diagrams from production snapshots
- packaged executables
- credentials or environment files

## Safety Model

- Read-only API calls.
- No device-side commands.
- No credentials in examples or output files.
- No traversal beyond the first upstream boundary pair.
- Output is designed for review, not execution.

## Security Review

Dependencies are monitored with Snyk. Vulnerability findings should be reviewed, remediated with explicit dependency updates, and validated with the sanitized test suite before release.

## Usage

Before running this against a real Forward Networks environment, confirm:

- your Forward Networks tenant/base URL
- your network or tenant-scoped network ID
- the authentication method approved for your tenant
- whether your tenant uses the default API prefix, such as `/api`
- the snapshot, device, topology, and snapshot-file endpoint structure exposed by your tenant
- the CDP/LLDP file naming convention available in the snapshot

Forward Networks deployments can differ by tenant, API version, and enabled features. Treat the endpoint templates in this sample as starting points, not universal constants.

Render from the included sanitized local payload:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m forward_topology_mapper.cli `
  --hostname ACCESS-SW01 `
  --local-payload examples\sanitized-topology.json `
  --output-dir output
```

Run against a reviewed Forward Networks snapshot:

```powershell
$env:FORWARD_NETWORKS_KEY = "your-key"
$env:FORWARD_NETWORKS_SECRET = "your-secret"
$env:FORWARD_NETWORKS_NETWORK_ID = "your-network-id"
$env:PYTHONPATH = "$PWD\src"
python -m forward_topology_mapper.cli --hostname access-sw01.example.net
```

Optional arguments can select a specific snapshot, output folder, tenant base URL, API prefix, auth mode, or endpoint template.

## Optional Windows Build

Install PyInstaller in your build environment, then run:

```powershell
python -m PyInstaller --noconfirm --clean .\ForwardNetworksTopologyMapper.spec
```

Generated executables, build folders, and logs should stay out of the public repository.

## Tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

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
- Report-style SVG with a map summary, legend, upstream boundary lane, adaptive downstream layout, and complete neighbor lookup table.

See:

- `examples/sample-topology-map.svg`
- `docs/example-topology-blueprint.md`
- `docs/example-network-map.svg`
