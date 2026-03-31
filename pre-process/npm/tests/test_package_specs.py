from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import PROJECT_ROOT

from pipeline.package_specs import NpmPackageSpec, load_package_specs, parse_package_spec


class PackageSpecParsingTests(unittest.TestCase):
    def test_parse_unscoped_package(self) -> None:
        parsed = parse_package_spec("is-odd")

        self.assertEqual(parsed, NpmPackageSpec(name="is-odd"))

    def test_parse_scoped_package(self) -> None:
        parsed = parse_package_spec("@types/node")

        self.assertEqual(parsed, NpmPackageSpec(name="@types/node"))

    def test_parse_package_rejects_version_suffix(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected package name without version"):
            parse_package_spec("left-pad@1.3.0")

    def test_parse_scoped_package_rejects_version_suffix(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected package name without version"):
            parse_package_spec("@types/node@24.0.0")

    def test_parse_scoped_package_rejects_missing_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected `@scope/name`"):
            parse_package_spec("@types")

    def test_load_package_specs_deduplicates_and_skips_comments(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            package_file = Path(temp_dir) / "package-list.txt"
            package_file.write_text(
                "\n".join(
                    (
                        "# comment",
                        "",
                        "is-odd",
                        "@types/node",
                        "is-odd",
                    )
                ),
                encoding="utf-8",
            )

            specs = load_package_specs(
                specs=["left-pad", "@types/node"],
                package_file=package_file,
            )

        self.assertEqual(
            specs,
            [
                NpmPackageSpec(name="left-pad"),
                NpmPackageSpec(name="@types/node"),
                NpmPackageSpec(name="is-odd"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
