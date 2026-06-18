from pathlib import Path
import tempfile
import unittest

from forward_topology_mapper.models import DeviceMetadata, NeighborLink, TopologyBlueprint
from forward_topology_mapper.render import render_markdown, render_svg, write_blueprint


class RenderTests(unittest.TestCase):
    def test_renders_markdown_and_svg(self):
        blueprint = TopologyBlueprint(
            target=DeviceMetadata(
                hostname="ACCESS-SW01",
                ip_address="192.0.2.10",
                device_type="Catalyst Access Switch",
                location="IDF-A",
                role="access",
            ),
            snapshot_id="snap-1",
            boundary_pattern=r"(core|router)",
            neighbors=(
                NeighborLink(
                    local_interface="Te1/1/1",
                    neighbor_hostname="CORE-RTR01",
                    remote_port="Te0/0/1",
                    protocol="LLDP",
                    neighbor_ip="192.0.2.1",
                    is_boundary=True,
                ),
            ),
        )

        markdown = render_markdown(blueprint, "map.svg")
        svg = render_svg(blueprint)

        self.assertIn("ACCESS-SW01", markdown)
        self.assertIn("CORE-RTR01", markdown)
        self.assertIn("192.0.2.1", markdown)
        self.assertIn("Traversal boundary", svg)

    def test_write_blueprint_creates_docs_files(self):
        blueprint = TopologyBlueprint(
            target=DeviceMetadata("ACCESS-SW01", "192.0.2.10", "switch", "IDF-A", "access"),
            snapshot_id="snap-1",
            boundary_pattern=r"(core|router)",
            neighbors=(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = write_blueprint(blueprint, Path(temp_dir))

            self.assertTrue(result.markdown_path.exists())
            self.assertTrue(result.svg_path.exists())

    def test_public_sample_topology_map_svg_is_included(self):
        sample_svg = Path(__file__).resolve().parents[1] / "examples" / "sample-topology-map.svg"

        self.assertTrue(sample_svg.exists())
        self.assertIn("ACCESS-SW01", sample_svg.read_text(encoding="utf-8"))

    def test_small_downstream_neighbor_set_renders_inline(self):
        blueprint = TopologyBlueprint(
            target=DeviceMetadata("ACCESS-SW01", "192.0.2.10", "switch", "IDF-A", "access"),
            snapshot_id="snap-1",
            boundary_pattern=r"(core|router)",
            neighbors=(
                NeighborLink("Gi1/0/12", "AP-01", "eth0", "CDP", is_boundary=False),
            ),
        )

        svg = render_svg(blueprint)

        self.assertIn("Downstream One-Hop Neighbors", svg)
        self.assertNotIn("Cards are arranged by local interface sort order", svg)

    def test_large_downstream_neighbor_set_uses_grid(self):
        links = tuple(
            NeighborLink(f"Gi1/0/{index}", f"AP-{index:02d}", "eth0", "CDP", is_boundary=False)
            for index in range(1, 6)
        )
        blueprint = TopologyBlueprint(
            target=DeviceMetadata("ACCESS-SW01", "192.0.2.10", "switch", "IDF-A", "access"),
            snapshot_id="snap-1",
            boundary_pattern=r"(core|router)",
            neighbors=links,
        )

        svg = render_svg(blueprint)

        self.assertIn("Cards are arranged by local interface sort order", svg)


if __name__ == "__main__":
    unittest.main()
