from __future__ import annotations

import unittest

from support import PROJECT_ROOT

from adapters.proxy_client import escape_module_path, escape_module_version, GoProxyClient


class ProxyEscapingTests(unittest.TestCase):
    def test_escape_module_path_matches_go_proxy_uppercase_rules(self) -> None:
        self.assertEqual(
            escape_module_path("GitHub.com/Google/UUID"),
            "!git!hub.com/!google/!u!u!i!d",
        )

    def test_escape_module_version_matches_go_proxy_uppercase_rules(self) -> None:
        self.assertEqual(escape_module_version("V1.2.3-RC1"), "!v1.2.3-!r!c1")

    def test_escape_module_path_rejects_bang(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot contain `!`"):
            escape_module_path("example.com/with!bang")

    def test_escape_module_version_rejects_non_ascii(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be ASCII"):
            escape_module_version("v1.0.0-你好")

    def test_build_mod_url_uses_escaped_tokens(self) -> None:
        client = GoProxyClient(base_url="https://proxy.example.test/")

        url = client.build_mod_url("GitHub.com/Google/UUID", "V1.2.3-RC1")

        self.assertEqual(
            url,
            "https://proxy.example.test/!git!hub.com/!google/!u!u!i!d/@v/!v1.2.3-!r!c1.mod",
        )

    def test_build_list_url_uses_escaped_module_path(self) -> None:
        client = GoProxyClient(base_url="https://proxy.example.test/")

        url = client.build_list_url("GitHub.com/Google/UUID")

        self.assertEqual(
            url,
            "https://proxy.example.test/!git!hub.com/!google/!u!u!i!d/@v/list",
        )


if __name__ == "__main__":
    unittest.main()
