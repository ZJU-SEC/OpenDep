from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class GoModuleModfileRecord:
    module_path: str
    version: str
    raw_mod: str
    raw_mod_sha256: str
    source_url: str
    fetched_at: datetime

    @classmethod
    def from_raw_mod(
        cls,
        *,
        module_path: str,
        version: str,
        raw_mod: str,
        source_url: str,
        fetched_at: datetime | None = None,
    ) -> "GoModuleModfileRecord":
        return cls(
            module_path=module_path,
            version=version,
            raw_mod=raw_mod,
            raw_mod_sha256=hashlib.sha256(raw_mod.encode("utf-8")).hexdigest(),
            source_url=source_url,
            fetched_at=fetched_at or datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "module_path": self.module_path,
            "version": self.version,
            "raw_mod_sha256": self.raw_mod_sha256,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(),
        }
