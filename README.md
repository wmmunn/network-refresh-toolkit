# Network Refresh Toolkit

Python tooling experiments for making network switch refresh work more repeatable, reviewable, and operator-safe.

This repository is a sanitized portfolio version of practical workflow tools. It uses placeholder hostnames, documentation-only examples, and test-style fixtures instead of private configs, logs, credentials, or environment-specific data.

## Why This Exists

Network refresh work often combines many small but risky tasks:

- collecting the current running configuration
- identifying uplinks and directly attached neighbors
- preserving switch metadata for a change package
- reviewing generated artifacts before live work
- keeping operators in control of any execution step

The tools represented here focus on turning those repeated tasks into readable artifacts and controlled workflows.

## Featured Work

### Forward Topology Mapper

Creates a switch-refresh topology sheet from a network snapshot.

The mapper is designed to:

- authenticate through environment variables
- query a read-only network snapshot
- locate a target access switch
- identify upstream gateway/router boundary devices
- parse one-hop CDP/LLDP neighbor output
- enrich switch and neighbor records with management IPs
- produce a Markdown lookup sheet
- produce a large screen-view SVG diagram

Example output:

- [Example topology blueprint](docs/example-topology-blueprint.md)
- [Example network map SVG](docs/example-network-map.svg)

### Forward Config Downloader

Downloads one switch running configuration from a reviewed network snapshot.

The downloader is designed to:

- authenticate through environment variables
- select the latest completed snapshot or a specific snapshot
- locate a switch by hostname
- read paged file-content responses
- write a plain text running-config artifact for operator review

Example output:

- [Example running config](examples/example-running-config.txt)

## Design Principles

- Read-only API access by default.
- No device-side commands for collection tools.
- Credentials are never stored in source, fixtures, logs, or examples.
- Inputs and outputs are explicit.
- Generated artifacts are meant to be reviewed by a network operator.
- Live execution workflows require operator control and visible safety gates.
- Tests and examples use sanitized fixtures only.

## Sanitized Example Data

The example topology uses placeholder devices and documentation IP ranges:

- `access-sw01.example.net`
- `core-gw01.example.net`
- `core-gw02.example.net`
- `ap-101.example.net`
- `camera-201.example.net`
- `phone-301.example.net`
- `192.0.2.0/24`
- `198.51.100.0/24`

These are not production hostnames or addresses.

## Repository Layout

```text
network-refresh-toolkit/
  README.md
  PRIVACY.md
  docs/
    example-topology-blueprint.md
    example-network-map.svg
  examples/
    sanitized-topology.json
    example-running-config.txt
  tools/
    forward-topology-mapper/
      README.md
    forward-config-downloader/
      README.md
      requirements.txt
      src/
      tests/
```

## What This Demonstrates

This project is meant to show practical network automation judgment:

- parsing semi-structured network command output
- normalizing data into operator-readable artifacts
- building safety boundaries around automation
- documenting assumptions separately from confirmed behavior
- creating useful tooling without exposing private operational material

## Status

Sanitized portfolio package. The Forward Config Downloader includes public sample source and tests; other tools may be represented by documentation and generated sanitized examples until their source is prepared for public release.
