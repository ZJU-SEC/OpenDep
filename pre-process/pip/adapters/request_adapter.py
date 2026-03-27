from __future__ import annotations

from pathlib import Path

from pip_models import BuildRequest


def _load_project_specs_file(project_file: str) -> list[str]:
    path = Path(project_file).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"project file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"project file is not a file: {path}")

    specs: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--"):
            raise ValueError(f"invalid package spec in project file at line {line_number}: {stripped}")
        if stripped in seen:
            continue
        seen.add(stripped)
        specs.append(stripped)

    if not specs:
        raise ValueError(f"project file does not contain any package names: {path}")
    return specs


def _parse_project_spec(raw_value: str) -> tuple[str, tuple[str, ...]]:
    value = raw_value.strip()
    if not value:
        raise ValueError("package spec cannot be empty")
    if "==" not in value:
        return value, ()
    name, version = value.split("==", 1)
    normalized_name = name.strip()
    normalized_version = version.strip()
    if not normalized_name or not normalized_version:
        raise ValueError(f"invalid package spec: {raw_value}")
    return normalized_name, (normalized_version,)


class BuildRequestAdapter:
    def from_cli_args(self, args) -> list[BuildRequest]:
        requests: list[BuildRequest] = []
        project_specs = list(getattr(args, "projects", []) or [])
        project_file = getattr(args, "project_file", None)
        if project_file:
            project_specs.extend(_load_project_specs_file(project_file))

        if project_specs and (args.name or args.version):
            raise ValueError("`--name` and `--version` are only supported for direct single-artifact runs")
        if not project_specs and (args.limit is not None or args.include_yanked):
            if not args.artifacts:
                raise ValueError("`--limit` and `--include-yanked` require `--project` or `--project-file` inputs")

        for artifact in args.artifacts:
            version_overrides: tuple[str, ...] = ()
            if args.name or args.version:
                if len(args.artifacts) != 1 or project_specs:
                    raise ValueError("`--name` and `--version` are only supported for direct single-artifact runs")
                if args.version:
                    version_overrides = (args.version,)
            requests.append(
                BuildRequest(
                    artifact_path=str(Path(artifact)),
                    project_name=args.name,
                    versions=version_overrides,
                )
            )

        for raw_project in project_specs:
            project_name, explicit_versions = _parse_project_spec(raw_project)
            requests.append(
                BuildRequest(
                    project_name=project_name,
                    versions=explicit_versions,
                    limit=args.limit,
                    include_yanked=args.include_yanked,
                    mirror_dir=args.mirror_dir,
                )
            )

        if not requests:
            raise ValueError("provide at least one artifact path, `--project`, `--project-file`, or use `--manifest`")
        return requests


__all__ = ["BuildRequestAdapter"]
