from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class NpmPackumentRecord:
    name: str
    raw_packument: str
    raw_packument_sha256: str
    source_url: str
    fetched_at: datetime
    source_rev: str | None = None

    @classmethod
    def from_raw_packument(
        cls,
        *,
        name: str,
        raw_packument: str,
        source_url: str,
        fetched_at: datetime | None = None,
        source_rev: str | None = None,
    ) -> "NpmPackumentRecord":
        return cls(
            name=name,
            raw_packument=raw_packument,
            raw_packument_sha256=hashlib.sha256(raw_packument.encode("utf-8")).hexdigest(),
            source_url=source_url,
            fetched_at=fetched_at or datetime.now(timezone.utc),
            source_rev=source_rev,
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "raw_packument_sha256": self.raw_packument_sha256,
            "source_url": self.source_url,
            "source_rev": self.source_rev,
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class NpmSyncCheckpointRecord:
    source_key: str
    registry_base_url: str
    changes_url: str
    last_seq: str | None = None
    checkpointed_at: datetime | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_key": self.source_key,
            "registry_base_url": self.registry_base_url,
            "changes_url": self.changes_url,
            "last_seq": self.last_seq,
            "checkpointed_at": self.checkpointed_at.isoformat() if self.checkpointed_at else None,
        }


@dataclass(frozen=True, slots=True)
class NpmTombstoneRecord:
    name: str
    source_rev: str | None
    deleted_seq: str | None
    deleted_at: datetime

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "source_rev": self.source_rev,
            "deleted_seq": self.deleted_seq,
            "deleted_at": self.deleted_at.isoformat(),
        }
