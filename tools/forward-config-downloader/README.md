# Forward Config Downloader

Sanitized portfolio summary of a read-only running-config retrieval tool.

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

## Safety Model

- Read-only API calls.
- No live device login.
- No device-side commands.
- No credentials in source, examples, logs, or output.
- Output is a review artifact, not an execution plan.

## Example

See `examples/example-running-config.txt` for a sanitized config artifact.
