from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitIndexError(RuntimeError):
    """Raised when a managed Cargo index git operation fails."""


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    command = ["git", *args]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = stderr or stdout or f"git command failed: {' '.join(command)}"
        raise GitIndexError(message) from exc
    return completed.stdout.strip()


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def describe_index_repo(path: Path) -> dict[str, object]:
    repo_exists = path.exists()
    git_repo = repo_exists and is_git_repo(path)
    payload: dict[str, object] = {
        "path": str(path),
        "exists": repo_exists,
        "git_repo": git_repo,
        "head": None,
        "branch": None,
        "origin_url": None,
        "dirty": None,
    }

    if not git_repo:
        return payload

    payload["head"] = _run_git(["rev-parse", "--short", "HEAD"], cwd=path)
    payload["branch"] = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    payload["origin_url"] = _run_git(["remote", "get-url", "origin"], cwd=path)
    payload["dirty"] = bool(_run_git(["status", "--short"], cwd=path))
    return payload


def clone_index(index_url: str, destination: Path, *, force: bool = False) -> dict[str, object]:
    if destination.exists():
        if not force:
            raise GitIndexError(
                f"managed index destination already exists: {destination}; rerun with --force to replace it"
            )
        shutil.rmtree(destination)

    staging = destination.parent / f".{destination.name}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run_git(["clone", "--depth", "1", index_url, str(staging)])
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return describe_index_repo(destination)


def update_index(destination: Path, *, force: bool = False) -> dict[str, object]:
    if not destination.exists():
        raise GitIndexError(f"managed index clone does not exist: {destination}")
    if not is_git_repo(destination):
        raise GitIndexError(f"managed index path is not a git repository: {destination}")

    before = describe_index_repo(destination)
    if before["dirty"]:
        if not force:
            raise GitIndexError(
                f"managed index clone has local modifications and cannot be updated safely: {destination}; rerun with --force to discard them"
            )

    branch = str(before["branch"] or "")
    if not branch or branch == "HEAD":
        raise GitIndexError(
            f"managed index clone is not on a named branch and cannot be updated safely: {destination}"
        )

    _run_git(["fetch", "--depth", "1", "origin", branch], cwd=destination)
    _run_git(["reset", "--hard", f"origin/{branch}"], cwd=destination)
    after = describe_index_repo(destination)
    return {
        "path": str(destination),
        "before_head": before["head"],
        "after_head": after["head"],
        "branch": after["branch"],
        "origin_url": after["origin_url"],
        "dirty": after["dirty"],
    }
