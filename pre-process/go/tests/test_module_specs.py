from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import PROJECT_ROOT

from pipeline.module_specs import (
    GoModuleRequest,
    GoModuleSpec,
    load_module_requests,
    load_module_specs,
    parse_module_request,
    parse_module_spec,
)


class ModuleSpecParsingTests(unittest.TestCase):
    def test_parse_module_request_allows_unversioned_module(self) -> None:
        parsed = parse_module_request("example.com/module")

        self.assertEqual(
            parsed,
            GoModuleRequest(module_path="example.com/module", version=None),
        )

    def test_parse_module_request_keeps_at_in_module_path_when_suffix_is_not_version(self) -> None:
        parsed = parse_module_request("example.com/ns@sub/module")

        self.assertEqual(
            parsed,
            GoModuleRequest(module_path="example.com/ns@sub/module", version=None),
        )

    def test_parse_module_spec_uses_last_at_separator(self) -> None:
        parsed = parse_module_spec("example.com/ns@sub/module@v1.2.3")

        self.assertEqual(
            parsed,
            GoModuleSpec(module_path="example.com/ns@sub/module", version="v1.2.3"),
        )

    def test_parse_module_spec_rejects_missing_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "version is empty"):
            parse_module_spec("example.com/module@")

    def test_parse_module_spec_rejects_missing_separator(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected `module@version`"):
            parse_module_spec("example.com/module")

    def test_load_module_specs_deduplicates_and_skips_comments(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            module_file = Path(temp_dir) / "module-list.txt"
            module_file.write_text(
                "\n".join(
                    (
                        "# comment",
                        "",
                        "example.com/a@v1.0.0",
                        "example.com/b@v2.0.0",
                        "example.com/a@v1.0.0",
                    )
                ),
                encoding="utf-8",
            )

            specs = load_module_specs(
                specs=["example.com/c@v3.0.0", "example.com/b@v2.0.0"],
                module_file=module_file,
            )

        self.assertEqual(
            specs,
            [
                GoModuleSpec(module_path="example.com/c", version="v3.0.0"),
                GoModuleSpec(module_path="example.com/b", version="v2.0.0"),
                GoModuleSpec(module_path="example.com/a", version="v1.0.0"),
            ],
        )

    def test_load_module_requests_allows_mixed_versioned_and_unversioned_inputs(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            module_file = Path(temp_dir) / "module-list.txt"
            module_file.write_text(
                "\n".join(
                    (
                        "# comment",
                        "example.com/a",
                        "example.com/b@v2.0.0",
                        "example.com/a",
                    )
                ),
                encoding="utf-8",
            )

            requests = load_module_requests(
                specs=["example.com/c@v3.0.0"],
                module_file=module_file,
            )

        self.assertEqual(
            requests,
            [
                GoModuleRequest(module_path="example.com/c", version="v3.0.0"),
                GoModuleRequest(module_path="example.com/a", version=None),
                GoModuleRequest(module_path="example.com/b", version="v2.0.0"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
