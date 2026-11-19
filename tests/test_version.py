"""One version in every place that states it: the plugin's manifest, the marketplace's metadata and the library."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support  # noqa: F401  (puts lib/ on the path)

from broom import __version__

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_the_manifest_the_marketplace_and_the_library_state_one_version(self) -> None:
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())["metadata"]["version"]
        self.assertEqual((market, __version__), (plugin, plugin))


if __name__ == "__main__":
    unittest.main()
