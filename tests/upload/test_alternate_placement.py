"""Tests for alternate-worker upload placement (CW-06).

Isolated: temporary SQLite database (foreign keys enforced) and an in-memory fake worker
client with fault injection. No live deployment or worker is touched.
"""
import hashlib
import io
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db import models as M
from app.repositories import object_repository as object_repo_module
from app.scheduler.replication import ReplicationManager
from app.services.object_service import ObjectService
from app.services.worker_client import WorkerClient
from shared.exceptions import ChunkNotFoundError, WorkerUnavailableError
from shared.models import ChunkVerifyResult

CHUNK = 1024  # small chunk size for multi-chunk tests


def url(w):
    return f"http://{w}:8001"


class FakeWorkers(WorkerClient):
    """Fake WorkerClient (no network). Per-worker PUT behaviour:
    ok | refuse | timeout_no_write | timeout_after_write | reject | corrupt."""

    def __init__(self):  # deliberately does not create the real HTTP client

        self.store: dict[tuple[str, str], bytes] = {}
        self.mode: dict[str, str] = {}
        self.puts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str, float | None]] = []
        self.hang_delete: set[str] = set()

    def _fail(self, base_url, cause):
        try:
            raise cause
        except httpx.HTTPError as e:
            raise WorkerUnavailableError(f"Failed to PUT to {base_url}") from e

    def put_chunk(self, base_url, chunk_id, data):
        self.puts.append((base_url, chunk_id))
        mode = self.mode.get(base_url, "ok")
        if mode == "refuse":
            self._fail(base_url, httpx.ConnectError("connection refused"))
        if mode == "timeout_no_write":
            self._fail(base_url, httpx.ReadTimeout("timed out"))
        if mode == "timeout_after_write":
            self.store[(base_url, chunk_id)] = bytes(data)       # worker wrote it, response lost
            self._fail(base_url, httpx.ReadTimeout("timed out"))
        if mode == "reject":
            self._fail(base_url, httpx.HTTPStatusError("500", request=httpx.Request("PUT", base_url),
                                                       response=httpx.Response(500)))
        self.store[(base_url, chunk_id)] = b"garbage" if mode == "corrupt" else bytes(data)

    def verify_chunk(self, base_url, chunk_id):
        b = self.store.get((base_url, chunk_id))
        if b is None:
            return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
        return ChunkVerifyResult(chunk_id=chunk_id, exists=True, checksum=hashlib.sha256(b).hexdigest(), size_bytes=len(b))

    def get_chunk(self, base_url, chunk_id):
        if (base_url, chunk_id) not in self.store:
            raise ChunkNotFoundError(chunk_id)
        return self.store[(base_url, chunk_id)]

    def delete_chunk(self, base_url, chunk_id, timeout=None):
        self.deletes.append((base_url, chunk_id, timeout))
        if base_url in self.hang_delete:
            raise WorkerUnavailableError("delete timed out")
        self.store.pop((base_url, chunk_id), None)

    def files(self, prefix=""):
        return sorted((u.split("//")[1].split(":")[0], c) for (u, c) in self.store if c.startswith(prefix))


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'meta.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        for w in ("w1", "w2", "w3", "w4"):
            db.add(M.Worker(id=w, base_url=url(w), status="active", used_bytes=0,
                            last_heartbeat=datetime.now(timezone.utc)))
        db.commit()
    yield factory
    engine.dispose()


def upload(factory, fake, data, chunk_size=1024 * 1024):
    db = factory()
    svc = ObjectService(db)
    svc.settings = Settings(chunk_size_bytes=chunk_size)
    svc.chunk_service.settings = Settings(chunk_size_bytes=chunk_size, worker_cleanup_timeout_seconds=2.0)
    svc.chunk_service.worker_client = fake
    try:
        obj = svc.upload("t.bin", "application/octet-stream", io.BytesIO(data), {})
        return obj.id
    finally:
        db.close()


def rows(factory):
    with factory() as db:
        return {
            "objects": [(o.id, o.status) for o in db.query(M.StoredObject)],
            "chunks": sorted(c.id for c in db.query(M.Chunk)),
            "replicas": sorted((r.chunk_id, r.worker_id, r.status) for r in db.query(M.ChunkReplica)),
            "used": {w.id: w.used_bytes for w in db.query(M.Worker)},
        }


DATA = b"x" * 700


# --------------------------------------------------------------------------- 1
def test_initial_selection_succeeds(env):
    fake = FakeWorkers()
    oid = upload(env, fake, DATA)
    r = rows(env)
    assert r["objects"] == [(oid, "available")]
    assert [w for _, w, s in r["replicas"]] == ["w1", "w2"]          # existing ranking unchanged
    assert fake.puts == [(url("w1"), f"{oid}_0"), (url("w2"), f"{oid}_0")]


# --------------------------------------------------------------------------- 2 / 7 / 8
def test_first_selected_worker_fails_alternate_succeeds(env):
    fake = FakeWorkers()
    fake.mode[url("w1")] = "refuse"
    oid = upload(env, fake, DATA)
    r = rows(env)
    assert r["objects"] == [(oid, "available")]
    assert r["replicas"] == [(f"{oid}_0", "w2", "stored"), (f"{oid}_0", "w3", "stored")]   # alternate recorded
    assert ("w1", f"{oid}_0") not in fake.files()                    # nothing stored for the failed worker
    assert r["used"]["w1"] == 0 and r["used"]["w3"] == len(DATA)      # accounting on the alternate only


# --------------------------------------------------------------------------- 3
def test_selected_worker_times_out_alternate_succeeds(env):
    fake = FakeWorkers()
    fake.mode[url("w2")] = "timeout_no_write"
    oid = upload(env, fake, DATA)
    assert [w for _, w, _ in rows(env)["replicas"]] == ["w1", "w3"]
    assert (url("w2"), f"{oid}_0", 2.0) in fake.deletes                # uncertain copy cleanup, short timeout


# --------------------------------------------------------------------------- 4
def test_multiple_selected_workers_fail_another_candidate_succeeds(env):
    fake = FakeWorkers()
    fake.mode.update({url("w1"): "refuse", url("w2"): "reject"})
    oid = upload(env, fake, DATA)
    assert [w for _, w, _ in rows(env)["replicas"]] == ["w3", "w4"]
    assert rows(env)["objects"] == [(oid, "available")]


# --------------------------------------------------------------------------- 5 / 10
def test_upload_fails_cleanly_when_candidates_are_exhausted(env):
    fake = FakeWorkers()
    fake.mode.update({url("w1"): "refuse", url("w2"): "timeout_no_write", url("w3"): "reject"})
    with pytest.raises(WorkerUnavailableError) as exc:
        upload(env, fake, DATA)
    msg = str(exc.value)
    assert "1 succeeded" in msg and "w1: ConnectError" in msg and "http://" not in msg
    r = rows(env)
    assert r["objects"] == [] and r["chunks"] == [] and r["replicas"] == []   # nothing marked available / stored
    assert fake.files() == []                                         # w4's verified copy was removed too


def test_object_not_available_when_a_later_chunk_cannot_reach_rf(env):
    fake = FakeWorkers()
    calls = {"n": 0}
    original = fake.put_chunk

    def put(base_url, chunk_id, data):
        calls["n"] += 1
        if chunk_id.endswith("_1") and base_url != url("w1"):
            fake.mode[base_url] = "refuse"
        try:
            return original(base_url, chunk_id, data)
        finally:
            fake.mode.pop(base_url, None)

    fake.put_chunk = put
    with pytest.raises(WorkerUnavailableError):
        upload(env, fake, b"a" * CHUNK + b"b" * 10, chunk_size=CHUNK)
    r = rows(env)
    assert r["objects"] == [] and r["chunks"] == [] and r["replicas"] == []
    assert fake.files() == []                                         # chunk 0 copies cleaned up as well


# --------------------------------------------------------------------------- 6
def test_no_worker_is_tried_twice_for_the_same_chunk(env):
    fake = FakeWorkers()
    fake.mode.update({url("w1"): "refuse", url("w2"): "corrupt", url("w3"): "timeout_no_write"})
    with pytest.raises(WorkerUnavailableError):
        upload(env, fake, DATA)
    targets = [u for u, _ in fake.puts]
    assert len(targets) == len(set(targets)) == 4


# --------------------------------------------------------------------------- 7 (verification)
def test_unverified_copy_is_never_recorded(env):
    fake = FakeWorkers()
    fake.mode[url("w1")] = "corrupt"
    oid = upload(env, fake, DATA)
    assert [w for _, w, _ in rows(env)["replicas"]] == ["w2", "w3"]
    assert ("w1", f"{oid}_0") not in fake.files()                    # corrupt copy deleted


# --------------------------------------------------------------------------- 9
def test_timeout_after_physical_write_is_cleaned_and_not_recorded(env):
    fake = FakeWorkers()
    fake.mode[url("w1")] = "timeout_after_write"
    oid = upload(env, fake, DATA)
    r = rows(env)
    assert [w for _, w, _ in r["replicas"]] == ["w2", "w3"]          # no row for the uncertain worker
    assert len(r["replicas"]) == len(set((c, w) for c, w, _ in r["replicas"]))
    assert ("w1", f"{oid}_0") not in fake.files()                    # the file it did write was removed


def test_cleanup_failure_after_timeout_does_not_fail_the_upload(env):
    fake = FakeWorkers()
    fake.mode[url("w1")] = "timeout_after_write"
    fake.hang_delete = {url("w1")}
    oid = upload(env, fake, DATA)
    r = rows(env)
    assert r["objects"] == [(oid, "available")]
    assert [w for _, w, _ in r["replicas"]] == ["w2", "w3"]          # orphan copy on w1 stays unrecorded


# --------------------------------------------------------------------------- 11
def test_multiple_chunks_use_alternates_and_failed_worker_is_deprioritised(env):
    fake = FakeWorkers()
    fake.mode[url("w2")] = "timeout_no_write"
    oid = upload(env, fake, b"z" * (3 * CHUNK), chunk_size=CHUNK)
    r = rows(env)
    assert r["objects"] == [(oid, "available")] and len(r["chunks"]) == 3
    by_chunk = {}
    for c, w, s in r["replicas"]:
        assert s == "stored"
        by_chunk.setdefault(c, []).append(w)
    assert all(len(ws) == 2 and "w2" not in ws for ws in by_chunk.values())
    assert sum(1 for u, _ in fake.puts if u == url("w2")) == 1       # only one timeout paid per upload


# --------------------------------------------------------------------------- 12
def test_reconciliation_after_failed_upload_creates_nothing(env):
    fake = FakeWorkers()
    fake.mode.update({url("w1"): "refuse", url("w2"): "refuse", url("w3"): "refuse"})
    with pytest.raises(WorkerUnavailableError):
        upload(env, fake, DATA)
    puts_before = len(fake.puts)
    res = ReplicationManager(session_factory=env, worker_client=fake).reconcile_once()
    assert (res.under_replicated, res.attempted) == (0, 0)
    assert len(fake.puts) == puts_before and rows(env)["replicas"] == []


def test_reconciliation_after_successful_fallback_adds_no_copies(env):
    fake = FakeWorkers()
    fake.mode[url("w1")] = "timeout_after_write"
    upload(env, fake, DATA)
    before = rows(env)["replicas"]
    fake.mode.clear()
    res = ReplicationManager(session_factory=env, worker_client=fake).reconcile_once()
    assert res.under_replicated == 0 and rows(env)["replicas"] == before


# --------------------------------------------------------------------------- cleanup must not hide the original error
def test_cleanup_failure_does_not_mask_original_error(env, monkeypatch):
    fake = FakeWorkers()
    fake.mode.update({url("w1"): "refuse", url("w2"): "refuse", url("w3"): "refuse"})

    def broken_delete(self, _object_id):
        raise RuntimeError("database went away during cleanup")

    monkeypatch.setattr(object_repo_module.ObjectRepository, "delete", broken_delete)
    with pytest.raises(WorkerUnavailableError):                       # original error, not RuntimeError
        upload(env, fake, DATA)
