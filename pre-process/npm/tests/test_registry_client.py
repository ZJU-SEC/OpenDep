from __future__ import annotations

import unittest

from support import PROJECT_ROOT

from adapters.registry_client import NpmRegistryClient, escape_package_name


class RegistryClientTests(unittest.TestCase):
    def test_escape_unscoped_package_name(self) -> None:
        self.assertEqual(escape_package_name("left-pad"), "left-pad")

    def test_escape_scoped_package_name(self) -> None:
        self.assertEqual(escape_package_name("@types/node"), "@types%2Fnode")

    def test_escape_package_name_rejects_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "package name is required"):
            escape_package_name("   ")

    def test_build_packument_url_uses_escaped_package_name(self) -> None:
        client = NpmRegistryClient(base_url="https://registry.example.test/")

        url = client.build_packument_url("@types/node")

        self.assertEqual(url, "https://registry.example.test/@types%2Fnode")


if __name__ == "__main__":
    unittest.main()
