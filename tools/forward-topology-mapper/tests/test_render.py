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


if __name__ == "__main__":
    unittest.main()
