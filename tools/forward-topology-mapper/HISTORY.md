# Forward Networks Topology Mapper History

## 0.4.0 - 2026-06-17

- Added styled GUI controls, custom app icon, and clearer operator-facing version label.
- Improved generated SVG topology maps with report-style header, legend, role colors, adaptive downstream layout, and cleaner spacing.
- Kept small downstream neighbor sets inline in the main topology canvas and larger sets in a readable grid.
- Added tests for icon availability and adaptive downstream SVG layout.

## 0.3.0 - 2026-06-17

- Added a Tkinter GUI wrapper around the existing read-only topology mapper core.
- Added GUI support for API-backed runs and sanitized local JSON payload rendering.
- Polished the GUI with a read-only safety banner, run summary, credential detection status, hidden offline-test controls, progress status, and result-opening buttons.
- Switched the packaged `ForwardNetworksTopologyMapper.exe` to launch the GUI without a console window.
- Kept the CLI module available from source via `python -m forward_topology_mapper.cli`.
- Added a sanitized GUI settings test.

## 0.2.0 - 2026-06-17

- Added `forward_topology_mapper_cli.py` as a packaging launcher.
- Added `ForwardNetworksTopologyMapper.spec` for a console PyInstaller build.
- Added project `.gitignore` for generated caches, logs, build output, and executables.
- Added the topology mapper executable to the portable-output workflow.

## 0.1.0 - 2026-06-10

- Created first CLI module for one-switch Forward Networks topology blueprints.
- Added tolerant payload parsing for device metadata, inline CDP/LLDP neighbors, and graph-style link payloads.
- Added Markdown and SVG output written to `docs/` by default.
- Added sanitized local JSON fixture support for tests and endpoint discovery.
- Confirmed live workflow using Forward snapshot topology links, `{hostname},lldp.txt`, and `{hostname},cdp.txt`.
- Added screen-view SVG output with upstream boundaries above the access switch and downstream one-hop neighbors in a grid.
- Upcoming work should add broader sanitized fixtures for Forward device metadata, topology links, file-content responses, and CDP/LLDP command-output variations.
