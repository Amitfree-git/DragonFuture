from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dragonboat_ai.futures_agent.infrastructure.database.base import to_db_datetime, utc_now_naive
from dragonboat_ai.futures_agent.infrastructure.database.models import (
    FutDataBatchORM,
    FutDataManifestORM,
    FutRawArchiveORM,
)


class ManifestStatus(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ManifestRef:
    manifest_id: str
    batch_id: str
    status: ManifestStatus


@dataclass(frozen=True, slots=True)
class ArchiveRef:
    archive_id: str


class SqlAlchemyManifestStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create(
        self,
        *,
        manifest_id: str,
        source_policy: str,
        data_mode: str,
        status: ManifestStatus = ManifestStatus.PENDING,
    ) -> ManifestRef:
        batch_id = f"batch-{manifest_id}"
        started = utc_now_naive()
        with self.session_factory.begin() as session:
            existing = session.get(FutDataManifestORM, manifest_id)
            if existing is not None:
                batch = session.get(FutDataBatchORM, batch_id)
                if batch is None:
                    raise RuntimeError(f"manifest {manifest_id} exists without batch {batch_id}")
                return ManifestRef(
                    manifest_id=existing.manifest_id,
                    batch_id=batch.batch_id,
                    status=ManifestStatus(existing.status),
                )
            session.add(
                FutDataManifestORM(
                    manifest_id=manifest_id,
                    source_policy=source_policy,
                    data_mode=data_mode,
                    status=status.value,
                )
            )
            session.flush()
            session.add(
                FutDataBatchORM(
                    batch_id=batch_id,
                    source=source_policy,
                    started_at=started,
                    status=status.value,
                    manifest_id=manifest_id,
                )
            )
        return ManifestRef(manifest_id=manifest_id, batch_id=batch_id, status=status)

    def commit(self, manifest_id: str) -> None:
        completed = utc_now_naive()
        with self.session_factory.begin() as session:
            manifest = session.get(FutDataManifestORM, manifest_id)
            if manifest is None:
                raise KeyError(manifest_id)
            manifest.status = ManifestStatus.COMMITTED.value
            manifest.committed_at = completed
            batch = session.scalar(
                select(FutDataBatchORM).where(FutDataBatchORM.manifest_id == manifest_id)
            )
            if batch is not None:
                batch.status = ManifestStatus.COMMITTED.value
                batch.completed_at = completed

    def archive_raw(
        self,
        *,
        provider: str,
        request_digest: str,
        response_hash: str,
        received_at: datetime,
        license_id: str,
        storage_uri: str,
    ) -> ArchiveRef:
        with self.session_factory.begin() as session:
            existing = session.scalar(
                select(FutRawArchiveORM).where(
                    FutRawArchiveORM.provider == provider,
                    FutRawArchiveORM.request_digest == request_digest,
                    FutRawArchiveORM.response_hash == response_hash,
                )
            )
            if existing is not None:
                return ArchiveRef(archive_id=existing.archive_id)
            archive_id = uuid4().hex
            session.add(
                FutRawArchiveORM(
                    archive_id=archive_id,
                    provider=provider,
                    request_digest=request_digest,
                    response_hash=response_hash,
                    received_at=to_db_datetime(received_at),
                    license_id=license_id,
                    storage_uri=storage_uri,
                )
            )
            return ArchiveRef(archive_id=archive_id)
