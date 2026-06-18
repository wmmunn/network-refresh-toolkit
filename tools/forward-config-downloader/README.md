# Forward Config Downloader

[![Snyk: Config Downloader](https://snyk.io/test/github/wmmunn/network-refresh-toolkit/badge.svg?targetFile=tools%2Fforward-config-downloader%2Frequirements.txt)](https://snyk.io/test/github/wmmunn/network-refresh-toolkit?targetFile=tools%2Fforward-config-downloader%2Frequirements.txt)

Sanitized public source for a read-only running-config retrieval tool.

## Goal

Given a target switch hostname, retrieve its running configuration from a reviewed network snapshot and save it as a plain text artifact for operator review.

## Workflow

```text
1. Read API credentials from environment variables.
2. Select the latest completed snapshot or a specified snapshot.
3. Locate the target device by hostname.
4. Read the snapshot file-content endpoint.
5. Page through the file content as needed.
6. Write a reviewable running-config text artifact.
```

## Source Included

This public version includes a runnable Python package under `src/` and sanitized tests under `tests/`.

It intentionally does not include:

- private tenant IDs
- real hostnames or IP addresses
- raw Forward Networks payloads
- logs or downloaded configs
- packaged executables
- credentials or environment files

## Safety Model

- Read-only API calls.
- No live device login.
- No device-side commands.
- No credentials in source, examples, logs, or output.
- Output is a review artifact, not an execution plan.
- Structured logs redact credential-like fields and auth-style values.

## Security Review

Dependencies are monitored with Snyk. Vulnerability findings should be reviewed, remediated with explicit dependency updates, and validated with the sanitized test suite before release.

## Usage

Before running this against a real Forward Networks environment, obtain and confirm:

- Your Forward Networks tenant/base URL.
- Your network or tenant-scoped network ID.
- The authentication method approved for your tenant.
- Whether your tenant uses the default API prefix, such as `/api`.
- The snapshot/device endpoint structure exposed by your tenant.
- The running-config file naming convention and file-content endpoint shape.

Forward Networks deployments can differ by tenant, API version, and enabled features. Treat the endpoint templates in this sample as starting points, not universal constants.

## Tenant Discovery Notes

The hardest part of adapting this workflow is often not the Python logic; it is confirming how a specific Forward Networks tenant exposes snapshot files and device data.

In a real deployment, expect to verify the tenant-specific path through a few controlled attempts:

1. Confirm the base URL and API prefix.
2. Confirm how networks and snapshots are listed.
3. Confirm the field that identifies completed snapshots.
4. Confirm how devices are listed inside a snapshot.
5. Confirm whether the running config is embedded in the device payload or exposed through a file-content endpoint.
6. Confirm the exact config file name pattern, such as `{hostname},configuration.txt`.
7. Confirm whether the file-content endpoint must be paged by line ranges.

This sample keeps multiple candidate endpoint templates because real Forward Networks environments may expose equivalent data through different routes. The operator should review failed endpoint attempts in the local log, identify the path shape their tenant actually supports, and then narrow or override templates for that environment.

Set credentials and network ID through environment variables:

```powershell
$env:FORWARD_NETWORKS_KEY = "your-key"
$env:FORWARD_NETWORKS_SECRET = "your-secret"
$env:FORWARD_NETWORKS_NETWORK_ID = "your-network-id"
$env:PYTHONPATH = "$PWD\src"
python -m forward_config_downloader.cli --hostname access-sw01.example.net
```

Optional arguments can select a specific snapshot, output folder, tenant base URL, or API prefix:

```powershell
python -m forward_config_downloader.cli `
  --network-id your-network-id `
  --snapshot-id snapshot-id `
  --hostname access-sw01.example.net `
  --output-dir manifests
```

## Tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

## Example

See `examples/example-running-config.txt` for a sanitized config artifact.
