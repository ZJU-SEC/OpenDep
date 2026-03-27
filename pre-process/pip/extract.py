from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PIP_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]

for path in (PIP_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from pipeline.extractor import PipDependencyExtractor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pip-preprocess-extract",
        description="Extract pip dependency metadata from a local distribution artifact.",
    )
    parser.add_argument("artifact", help="Path to a local wheel / sdist / egg artifact.")
    parser.add_argument("--name", help="Optional package name override.")
    parser.add_argument("--version", help="Optional package version override.")
    parser.add_argument(
        "--no-legacy-fallback",
        action="store_true",
        help="Disable the legacy fallback extractor when the resolver inspector path fails.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the output JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extractor = PipDependencyExtractor()
    payload = extractor.extract_local_artifact(
        args.artifact,
        project_name=args.name,
        version=args.version,
        allow_legacy_fallback=not args.no_legacy_fallback,
    ).to_dict()
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
