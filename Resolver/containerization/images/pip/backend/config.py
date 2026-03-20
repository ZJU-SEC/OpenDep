from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


MetadataMode = Literal["live", "indexed"]


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class BackendConfig:
    metadata_mode: MetadataMode = "live"
    cache_dir: str | None = None
    index_backend: str | None = None
    index_dsn: str | None = None
    index_table: str = "projects_metadata"
    index_fallback_to_live: bool = False
    pypi_json_base_url: str = "https://pypi.org/pypi"
    http_user_agent: str = "OpenDep-Pip-Resolver/0.1"

    @classmethod
    def from_env(cls) -> "BackendConfig":
        raw_mode = os.getenv("PIP_METADATA_MODE", "live").strip().lower()
        metadata_mode: MetadataMode = "indexed" if raw_mode == "indexed" else "live"
        return cls(
            metadata_mode=metadata_mode,
            cache_dir=os.getenv("PIP_CACHE_DIR") or None,
            index_backend=os.getenv("PIP_INDEX_BACKEND") or None,
            index_dsn=os.getenv("PIP_INDEX_DSN") or None,
            index_table=os.getenv("PIP_INDEX_TABLE", "projects_metadata").strip() or "projects_metadata",
            index_fallback_to_live=_env_bool("PIP_INDEX_FALLBACK_TO_LIVE", default=False),
            pypi_json_base_url=(os.getenv("PIP_PYPI_JSON_BASE_URL") or "https://pypi.org/pypi").rstrip("/"),
            http_user_agent=os.getenv("PIP_HTTP_USER_AGENT") or "OpenDep-Pip-Resolver/0.1",
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "metadata_mode": self.metadata_mode,
            "cache_dir": self.cache_dir,
            "index_backend": self.index_backend,
            "index_dsn_configured": bool(self.index_dsn),
            "index_table": self.index_table,
            "index_fallback_to_live": self.index_fallback_to_live,
            "pypi_json_base_url": self.pypi_json_base_url,
            "http_user_agent": self.http_user_agent,
        }
