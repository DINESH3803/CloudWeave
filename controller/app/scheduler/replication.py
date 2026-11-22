"""Replication management: keep every chunk at the configured replication factor.

Restoration is level-triggered. Every call to ``reconcile_once`` re-derives the set of
under-replicated chunks from persistent metadata, so a repair that failed earlier is
retried on a later pass even if no worker changes state again, and a restarted
controller resumes from the database.

Each chunk is repaired in its own short-lived database session. A failed repair is
rolled back and cannot affect the repairs that follow it.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk, StoredObject, Worker
from app.db.session import SessionLocal
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.worker_repository import WorkerRepository
from app.scheduler.placement import LeastLoadedPlacement, PlacementStrategy
from app.services.worker_client import WorkerClient
from shared.constants import OBJECT_STATUS_AVAILABLE, REPLICA_STATUS_STORED, WORKER_STATUS_ACTIVE
from shared.models import WorkerInfo

logger = logging.getLogger(__name__)

# Only one reconciliation pass may run at a time in this controller process. The
# deployment has a single controller, so a process-local lock is sufficient.
_RECONCILE_LOCK = threading.Lock()


def _short(err: BaseException | str, limit: int = 200) -> str:
    """One-line, bounded error text for logs."""
    msg = str(err).strip()
    first = msg.splitlines()[0] if msg else ""
    if isinstance(err, BaseException):
        text = f"{type(err).__name__}: {first}" if first else type(err).__name__
    else:
        text = first
    return text[:limit]


@dataclass
class _RetryState:
    failures: int = 0
    next_attempt: float = 0.0
    last_reason: str = ""


@dataclass
class RepairOutcome:
    """Result of one repair attempt for one chunk."""

    replicas_added: int = 0
    satisfied: bool = False  # chunk has (or no longer needs) the desired number of usable replicas
    reason: str | None = None  # why it is still short, when not satisfied


@dataclass
class ReconcileResult:
    """Summary of one reconciliation pass."""

    under_replicated: int = 0
    attempted: int = 0
    restored: int = 0
    replicas_added: int = 0
    failed: int = 0
    deferred: int = 0
    skipped_busy: bool = False
    failed_chunks: list[str] = field(default_factory=list)


class ReplicationManager:
    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        placement: PlacementStrategy | None = None,
        worker_client: WorkerClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.settings = get_settings()
        self.placement = placement or LeastLoadedPlacement()
        self.worker_client = worker_client or WorkerClient(self.settings)
        self._clock = clock
        # In-memory retry/backoff bookkeeping. It is intentionally not persisted: after a
        # restart every under-replicated chunk is simply due again.
        self._retry: dict[str, _RetryState] = {}
        self._passes = 0

    # ------------------------------------------------------------------ discovery
    def find_under_replicated(self) -> list[str]:
        """IDs of chunks (of available objects) with fewer usable replicas than the RF.

        A replica is usable only if its status is ``stored`` and its worker is ``active``.
        """
        with self.session_factory() as db:
            chunks = ChunkRepository(db).find_under_replicated(self.settings.replication_factor)
            return [c.id for c in chunks]

    # ------------------------------------------------------------------ reconciliation
    def reconcile_once(self) -> ReconcileResult:
        """Run one level-triggered reconciliation pass. Never raises."""
        result = ReconcileResult()
        if not _RECONCILE_LOCK.acquire(blocking=False):
            result.skipped_busy = True
            logger.debug("Replication reconciliation already running; skipping this cycle")
            return result
        try:
            try:
                under_replicated = self.find_under_replicated()
            except Exception as e:
                logger.warning("Replication reconciliation could not read metadata (will retry next cycle): %s", _short(e))
                return result

            result.under_replicated = len(under_replicated)
            pending = set(under_replicated)
            # Forget backoff state for chunks that recovered or no longer exist.
            for chunk_id in list(self._retry):
                if chunk_id not in pending:
                    del self._retry[chunk_id]

            now = self._clock()
            due = [c for c in under_replicated if self._retry.get(c, _RetryState()).next_attempt <= now]
            result.deferred = len(under_replicated) - len(due)
            if under_replicated:
                logger.info(
                    "Replication reconciliation: %d under-replicated chunk(s), %d due now, %d in retry backoff",
                    len(under_replicated), len(due), result.deferred,
                )

            for chunk_id in due:
                result.attempted += 1
                try:
                    outcome = self._repair_chunk(chunk_id)
                except Exception as e:  # already rolled back inside _repair_chunk
                    outcome = RepairOutcome(reason=f"unexpected error: {_short(e)}")
                result.replicas_added += outcome.replicas_added
                if outcome.satisfied:
                    result.restored += 1
                    self._retry.pop(chunk_id, None)
                else:
                    result.failed += 1
                    result.failed_chunks.append(chunk_id)
                    self._record_failure(chunk_id, outcome.reason or "unknown reason")

            self._passes += 1
            if under_replicated or self._passes == 1:
                logger.info(
                    "Replication reconciliation pass %d: %d under-replicated, %d restored, %d replica(s) added, "
                    "%d failed, %d deferred",
                    self._passes, result.under_replicated, result.restored, result.replicas_added,
                    result.failed, result.deferred,
                )
            else:
                logger.debug("Replication reconciliation pass %d: all chunks at replication factor", self._passes)
            return result
        finally:
            _RECONCILE_LOCK.release()

    def restore_replication(self) -> ReconcileResult:
        """Backwards-compatible alias for :meth:`reconcile_once`."""
        return self.reconcile_once()

    def replicate_chunk(self, chunk_id: str) -> bool:
        """Repair a single chunk now (ignores backoff). Returns True if it reached the RF."""
        try:
            return self._repair_chunk(chunk_id).satisfied
        except Exception as e:
            logger.warning("Error re-replicating chunk %s: %s", chunk_id, _short(e))
            return False

    def _record_failure(self, chunk_id: str, reason: str) -> None:
        state = self._retry.setdefault(chunk_id, _RetryState())
        state.failures += 1
        delay = min(
            self.settings.replication_retry_base_seconds * (2 ** (state.failures - 1)),
            self.settings.replication_retry_max_seconds,
        )
        state.next_attempt = self._clock() + delay
        state.last_reason = reason
        logger.warning(
            "Replica restoration for chunk %s incomplete (attempt %d): %s; retrying in %.0fs",
            chunk_id, state.failures, reason, delay,
        )

    # ------------------------------------------------------------------ single-chunk repair
    def _repair_chunk(self, chunk_id: str) -> RepairOutcome:
        """Bring one chunk back to the RF using its own database session."""
        rf = self.settings.replication_factor
        db = self.session_factory()
        unrecorded: list[WorkerInfo] = []  # copies written but not yet recorded in metadata
        try:
            chunks = ChunkRepository(db)
            chunk = chunks.get_chunk(chunk_id)
            if chunk is None or not self._chunk_still_wanted(db, chunk_id):
                return RepairOutcome(satisfied=True)  # deleted meanwhile: nothing to restore

            usable = [
                r for r in chunk.replicas
                if r.status == REPLICA_STATUS_STORED and r.worker is not None and r.worker.status == WORKER_STATUS_ACTIVE
            ]
            deficit = rf - len(usable)
            if deficit <= 0:
                return RepairOutcome(satisfied=True)

            data = self._read_verified_source(chunk, usable)
            if data is None:
                return RepairOutcome(reason="no reachable source replica with a valid checksum")

            # Never write to a worker that already has any replica row for this chunk
            # (stored, corrupt, or on an unavailable worker): avoids duplicate records/copies.
            holders = {r.worker_id for r in chunk.replicas}
            candidates = [
                WorkerInfo(
                    worker_id=w.id, base_url=w.base_url, status=w.status,
                    capacity_bytes=w.capacity_bytes, used_bytes=w.used_bytes, last_heartbeat=w.last_heartbeat,
                )
                for w in WorkerRepository(db).list_by_status(WORKER_STATUS_ACTIVE)
                if w.id not in holders
            ]
            if not candidates:
                return RepairOutcome(reason="no eligible target worker (every active worker already holds a replica row)")

            ordered = self.placement.select_workers(chunk.chunk_index, candidates, len(candidates))
            added = 0
            last_error: str | None = None
            for target in ordered:
                if added >= deficit:
                    break
                try:
                    self.worker_client.put_chunk(target.base_url, chunk_id, data)
                except Exception as e:
                    last_error = f"write to {target.worker_id} failed: {_short(e)}"
                    logger.warning("Replica restoration for chunk %s: %s", chunk_id, last_error)
                    continue
                unrecorded.append(target)
                if not self._copy_verified(target, chunk_id, chunk.checksum):
                    last_error = f"copy on {target.worker_id} failed verification"
                    logger.warning("Replica restoration for chunk %s: %s; discarding it", chunk_id, last_error)
                    self._discard_copy(target, chunk_id)
                    unrecorded.remove(target)
                    continue
                if not self._chunk_still_wanted(db, chunk_id):
                    # Object deleted while we were copying: drop the copy we just wrote.
                    self._discard_copy(target, chunk_id)
                    unrecorded.remove(target)
                    return RepairOutcome(replicas_added=added, satisfied=True)
                chunks.add_replica(chunk_id, target.worker_id, status=REPLICA_STATUS_STORED)  # commits
                unrecorded.remove(target)
                added += 1
                self._bump_used_bytes(db, target.worker_id, len(data))
                logger.info(
                    "Restored replica of chunk %s on %s (%d/%d usable replicas)",
                    chunk_id, target.worker_id, len(usable) + added, rf,
                )

            if added >= deficit:
                return RepairOutcome(replicas_added=added, satisfied=True)
            return RepairOutcome(
                replicas_added=added,
                reason=last_error or f"only {len(usable) + added}/{rf} usable replicas possible with current workers",
            )
        except Exception as e:
            db.rollback()
            for target in unrecorded:
                self._discard_copy(target, chunk_id)
            logger.warning("Replica restoration for chunk %s rolled back: %s", chunk_id, _short(e))
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _chunk_still_wanted(db: Session, chunk_id: str) -> bool:
        return (
            db.query(Chunk.id)
            .join(StoredObject, Chunk.object_id == StoredObject.id)
            .filter(Chunk.id == chunk_id, StoredObject.status == OBJECT_STATUS_AVAILABLE)
            .first()
            is not None
        )

    def _read_verified_source(self, chunk: Chunk, usable: list) -> bytes | None:
        for rep in usable:
            try:
                raw = self.worker_client.get_chunk(rep.worker.base_url, chunk.id)
            except Exception as e:
                logger.warning("Replica restoration for chunk %s: source %s unreadable: %s", chunk.id, rep.worker_id, _short(e))
                continue
            if hashlib.sha256(raw).hexdigest() == chunk.checksum:
                return raw
            logger.warning("Replica restoration for chunk %s: checksum mismatch on source %s", chunk.id, rep.worker_id)
        return None

    def _copy_verified(self, target: WorkerInfo, chunk_id: str, expected_checksum: str) -> bool:
        try:
            res = self.worker_client.verify_chunk(target.base_url, chunk_id)
        except Exception as e:
            logger.warning("Verification of chunk %s on %s failed: %s", chunk_id, target.worker_id, _short(e))
            return False
        return bool(res.exists and res.checksum == expected_checksum)

    def _discard_copy(self, target: WorkerInfo, chunk_id: str) -> None:
        try:
            self.worker_client.delete_chunk(target.base_url, chunk_id)
        except Exception as e:
            logger.warning("Could not remove unrecorded copy of chunk %s from %s: %s", chunk_id, target.worker_id, _short(e))

    @staticmethod
    def _bump_used_bytes(db: Session, worker_id: str, nbytes: int) -> None:
        """Best-effort usage accounting (heartbeats overwrite it with the real value)."""
        try:
            db.query(Worker).filter(Worker.id == worker_id).update(
                {Worker.used_bytes: Worker.used_bytes + nbytes}, synchronize_session=False
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Could not update used_bytes for %s: %s", worker_id, _short(e))
