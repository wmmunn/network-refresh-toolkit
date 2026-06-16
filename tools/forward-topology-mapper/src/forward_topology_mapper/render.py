from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from .models import TopologyBlueprint, WriteResult


SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(value: str) -> str:
    cleaned = SAFE_FILENAME_PATTERN.sub("_", value.strip()).strip("._")
    return cleaned or "switch"


def write_blueprint(blueprint: TopologyBlueprint, output_dir: Path) -> WriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{safe_filename(blueprint.target.hostname)}__snapshot-{safe_filename(blueprint.snapshot_id)}"
    markdown_path = output_dir / f"{base_name}__topology-blueprint.md"
    svg_path = output_dir / f"{base_name}__network-map.svg"
    markdown_path.write_text(render_markdown(blueprint, svg_path.name), encoding="utf-8", newline="\n")
    svg_path.write_text(render_svg(blueprint), encoding="utf-8", newline="\n")
    return WriteResult(markdown_path=markdown_path, svg_path=svg_path)


def render_markdown(blueprint: TopologyBlueprint, svg_filename: str) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target = blueprint.target
    lines = [
        f"# Forward Networks Topology Blueprint: {target.hostname}",
        "",
        "## Source",
        "",
        f"- Snapshot ID: `{blueprint.snapshot_id}`",
        f"- Generated: `{generated_at}`",
        "- Scope: target switch plus active one-hop Forward topology/CDP/LLDP neighbors only.",
        f"- Traversal boundary: neighbors matching `{blueprint.boundary_pattern}` are included but not expanded.",
        "",
        "## Target Switch",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Hostname | `{target.hostname}` |",
        f"| Primary IP | `{target.ip_address}` |",
        f"| Device type | `{target.device_type}` |",
        f"| Location / IDF / closet | `{target.location}` |",
        "",
        "## Active Topology Neighbors",
        "",
        "| Local interface | Protocol | Neighbor | Neighbor IP | Remote port | Boundary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if blueprint.neighbors:
        for link in blueprint.neighbors:
            boundary = "Yes" if link.is_boundary else "No"
            neighbor_ip = link.neighbor_ip or "Unknown"
            lines.append(
                f"| `{link.local_interface}` | {link.protocol} | `{link.neighbor_hostname}` | `{neighbor_ip}` | `{link.remote_port}` | {boundary} |"
            )
    else:
        lines.append("| _None found_ |  |  |  |  |  |")
    lines.extend(["", "## Network Map", "", f"![Network map]({svg_filename})", ""])
    return "\n".join(lines)


def render_svg(blueprint: TopologyBlueprint) -> str:
    width = 1800
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    target = blueprint.target
    boundary_links = [link for link in blueprint.neighbors if link.is_boundary]
    access_links = [link for link in blueprint.neighbors if not link.is_boundary]
    display_links = boundary_links + access_links
    downstream_rows = max(1, (len(access_links) + 3) // 4)
    downstream_y = 780
    table_y = downstream_y + 88 + downstream_rows * 140
    height = max(1280, table_y + 520)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f6f8fb"/>',
        svg_styles(),
        f'<rect x="0" y="0" width="{width}" height="98" fill="#172033"/>',
        f'<rect x="0" y="94" width="{width}" height="4" fill="#2f80ed"/>',
        '<text x="42" y="40" class="hero">Switch Refresh Topology</text>',
        f'<text x="42" y="68" class="hero-sub">{escape(target.hostname)}</text>',
        f'<text x="1430" y="38" class="header-meta">Snapshot {escape(blueprint.snapshot_id)}</text>',
        f'<text x="1430" y="64" class="header-meta">Generated {escape(generated_at)}</text>',
        '<text x="42" y="136" class="section-title">Target Switch</text>',
        metric_tile(42, 154, "Management IP", target.ip_address, 390),
        metric_tile(462, 154, "Device Type", target.device_type, 390),
        metric_tile(882, 154, "Location / IDF", target.location, 390),
        metric_tile(1302, 154, "Boundary Rule", "gateway / router / core", 390),
        '<rect x="42" y="264" width="1716" height="430" rx="10" fill="#ffffff" stroke="#d8dee9"/>',
        '<text x="66" y="300" class="section-title">Upstream Boundary Map</text>',
        '<text x="66" y="324" class="muted">Traversal stops at the first upstream boundary pair. Downstream neighbors are listed below as direct one-hop LLDP/CDP adjacencies.</text>',
    ]

    switch_x = 700
    switch_y = 518
    switch_w = 400
    switch_h = 118
    parts.append(device_card(switch_x, switch_y, switch_w, switch_h, target.hostname, f"IP {target.ip_address}", "Access switch", "#1f2937", "#f9fafb"))

    if display_links:
        for index, link in enumerate(boundary_links):
            x = 360 + index * 700 if len(boundary_links) <= 2 else 170 + index * 390
            y = 360
            parts.append(device_card(x, y, 380, 90, link.neighbor_hostname, f"IP {link.neighbor_ip or 'Unknown'}", "Traversal boundary", "#047857", "#ecfdf5"))
            parts.append(topology_line(x + 190, y + 90, switch_x + switch_w // 2, switch_y, link.remote_port, link.local_interface, "#047857"))
    else:
        parts.append('<rect x="520" y="384" width="760" height="42" rx="6" fill="#fff7ed" stroke="#fed7aa"/>')
        parts.append('<text x="548" y="411" class="warn">No upstream boundary neighbors were found in the supplied Forward data.</text>')

    parts.extend(render_downstream_grid(access_links, y=downstream_y))
    parts.extend(render_uplink_table(display_links, table_y, width))
    parts.append("</svg>")
    return "\n".join(parts)


def distribute_y(index: int, count: int, height: int, top: int | None = None, bottom: int | None = None) -> int:
    if count <= 1:
        if top is not None and bottom is not None:
            return (top + bottom) // 2
        return height // 2
    usable_top = top if top is not None else 125
    usable_bottom = bottom if bottom is not None else height - 80
    return int(usable_top + index * ((usable_bottom - usable_top) / (count - 1)))


def box(x: int, y: int, width: int, height: int, fill: str, stroke: str, title: str, subtitle: str) -> str:
    title_text = escape(title)
    subtitle_text = escape(subtitle)
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        f'<text x="{x + 16}" y="{y + 30}" class="label" font-weight="700">{title_text}</text>'
        f'<text x="{x + 16}" y="{y + 52}" class="small">{subtitle_text}</text>'
    )


def line(x1: int, y1: int, x2: int, y2: int, local_interface: str, remote_port: str) -> str:
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#6b7280" stroke-width="2"/>'
        f'<circle cx="{x1}" cy="{y1}" r="4" fill="#111827"/>'
        f'<circle cx="{x2}" cy="{y2}" r="4" fill="#111827"/>'
        f'<text x="{mid_x - 88}" y="{mid_y - 8}" class="iface">local {escape(local_interface)}</text>'
        f'<text x="{mid_x - 88}" y="{mid_y + 10}" class="iface">remote {escape(remote_port)}</text>'
    )


def svg_styles() -> str:
    return (
        "<style>"
        "text{font-family:Segoe UI,Arial,sans-serif;letter-spacing:0}"
        ".hero{font-size:26px;font-weight:700;fill:#ffffff}"
        ".hero-sub{font-size:17px;fill:#cbd5e1}"
        ".header-meta{font-size:13px;fill:#dbeafe;text-anchor:start}"
        ".section-title{font-size:16px;font-weight:700;fill:#111827}"
        ".tile-label{font-size:11px;font-weight:700;fill:#64748b;text-transform:uppercase}"
        ".tile-value{font-size:16px;font-weight:700;fill:#111827}"
        ".device-title{font-size:15px;font-weight:700;fill:#111827}"
        ".device-sub{font-size:13px;fill:#374151}"
        ".muted{font-size:12px;fill:#64748b}"
        ".port{font-size:11px;font-weight:700;fill:#111827}"
        ".table-head{font-size:12px;font-weight:700;fill:#334155}"
        ".table-cell{font-size:12px;fill:#111827}"
        ".warn{font-size:13px;font-weight:700;fill:#9a3412}"
        "</style>"
    )


def metric_tile(x: int, y: int, label: str, value: str, width: int = 250) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="70" rx="8" fill="#ffffff" stroke="#d8dee9"/>'
        f'<text x="{x + 18}" y="{y + 24}" class="tile-label">{escape(label)}</text>'
        f'<text x="{x + 18}" y="{y + 52}" class="tile-value">{escape(fit(value, max(24, width // 11)))}</text>'
    )


def device_card(x: int, y: int, width: int, height: int, title: str, subtitle: str, caption: str, stroke: str, fill: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        f'<text x="{x + 18}" y="{y + 32}" class="device-title">{escape(fit(title, 30))}</text>'
        f'<text x="{x + 18}" y="{y + 58}" class="device-sub">{escape(fit(subtitle, 32))}</text>'
        f'<text x="{x + 18}" y="{y + 82}" class="muted">{escape(fit(caption, 32))}</text>'
    )


def topology_line(x1: int, y1: int, x2: int, y2: int, local_interface: str, remote_port: str, stroke: str) -> str:
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    label_width = 250
    label_x = mid_x - label_width // 2
    label_y = mid_y - 18
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="3"/>'
        f'<circle cx="{x1}" cy="{y1}" r="5" fill="#111827"/>'
        f'<circle cx="{x2}" cy="{y2}" r="5" fill="#111827"/>'
        f'<rect x="{label_x}" y="{label_y - 14}" width="{label_width}" height="54" rx="5" fill="#ffffff" stroke="#e5e7eb"/>'
        f'<text x="{label_x + 12}" y="{label_y + 1}" class="port">local: {escape(fit(local_interface, 34))}</text>'
        f'<text x="{label_x + 12}" y="{label_y + 22}" class="port">remote: {escape(fit(remote_port, 34))}</text>'
    )


def render_downstream_grid(links, y: int) -> list[str]:
    parts = [
        f'<text x="42" y="{y}" class="section-title">Downstream One-Hop Neighbors</text>',
        f'<text x="42" y="{y + 24}" class="muted">Direct LLDP/CDP neighbors below the access switch. Cards are arranged by local interface sort order for quick lookup.</text>',
    ]
    if not links:
        parts.append(f'<rect x="42" y="{y + 44}" width="1716" height="70" rx="10" fill="#ffffff" stroke="#d8dee9"/>')
        parts.append(f'<text x="66" y="{y + 88}" class="warn">No downstream LLDP/CDP neighbors were found.</text>')
        return parts

    card_w = 405
    card_h = 112
    gap_x = 24
    gap_y = 28
    start_x = 42
    start_y = y + 48
    for index, link in enumerate(links):
        col = index % 4
        row = index // 4
        x = start_x + col * (card_w + gap_x)
        card_y = start_y + row * (card_h + gap_y)
        parts.append(neighbor_card(x, card_y, card_w, card_h, link))
    return parts


def neighbor_card(x: int, y: int, width: int, height: int, link) -> str:
    stroke = "#4338ca" if link.protocol == "LLDP" else "#2563eb"
    fill = "#ffffff"
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="9" fill="{fill}" stroke="#d8dee9"/>'
        f'<rect x="{x}" y="{y}" width="7" height="{height}" rx="4" fill="{stroke}"/>'
        f'<text x="{x + 22}" y="{y + 28}" class="device-title">{escape(fit(link.neighbor_hostname, 36))}</text>'
        f'<text x="{x + 22}" y="{y + 52}" class="device-sub">IP {escape(fit(link.neighbor_ip or "Unknown", 24))}</text>'
        f'<text x="{x + 22}" y="{y + 76}" class="muted">Local {escape(fit(link.local_interface, 22))} -> Remote {escape(fit(link.remote_port, 20))}</text>'
        f'<text x="{x + 22}" y="{y + 98}" class="muted">{escape(link.protocol)}</text>'
    )


def render_uplink_table(links, y: int, width: int) -> list[str]:
    parts = [
        f'<text x="42" y="{y}" class="section-title">Complete Neighbor Lookup</text>',
        f'<rect x="42" y="{y + 18}" width="{width - 84}" height="{max(96, 44 + min(len(links), 12) * 26)}" rx="10" fill="#ffffff" stroke="#d8dee9"/>',
        f'<rect x="42" y="{y + 18}" width="{width - 84}" height="36" rx="10" fill="#e8eef7"/>',
        f'<text x="64" y="{y + 42}" class="table-head">Local Port</text>',
        f'<text x="246" y="{y + 42}" class="table-head">Neighbor</text>',
        f'<text x="680" y="{y + 42}" class="table-head">Neighbor IP</text>',
        f'<text x="880" y="{y + 42}" class="table-head">Remote Port</text>',
        f'<text x="1110" y="{y + 42}" class="table-head">Type</text>',
        f'<text x="1280" y="{y + 42}" class="table-head">Boundary</text>',
    ]
    if not links:
        parts.append(f'<text x="64" y="{y + 82}" class="table-cell">No topology neighbors found.</text>')
        return parts

    for index, link in enumerate(links[:12]):
        row_y = y + 82 + index * 26
        boundary = "Yes" if link.is_boundary else "No"
        parts.extend(
            [
                f'<text x="64" y="{row_y}" class="table-cell">{escape(fit(link.local_interface, 22))}</text>',
                f'<text x="246" y="{row_y}" class="table-cell">{escape(fit(link.neighbor_hostname, 52))}</text>',
                f'<text x="680" y="{row_y}" class="table-cell">{escape(fit(link.neighbor_ip or "Unknown", 18))}</text>',
                f'<text x="880" y="{row_y}" class="table-cell">{escape(fit(link.remote_port, 24))}</text>',
                f'<text x="1110" y="{row_y}" class="table-cell">{escape(fit(link.protocol, 14))}</text>',
                f'<text x="1280" y="{row_y}" class="table-cell">{boundary}</text>',
            ]
        )
    if len(links) > 12:
        parts.append(f'<text x="64" y="{y + 414}" class="muted">Plus {len(links) - 12} additional neighbors. See Markdown table for full list.</text>')
    return parts


def fit(value: str, max_chars: int) -> str:
    text = value or "Unknown"
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def escape(value: str) -> str:
    return html.escape(value, quote=True)
