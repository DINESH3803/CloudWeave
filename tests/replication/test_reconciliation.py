"""Tests for level-triggered replication reconciliation (CW-05).

Isolated: each test uses a temporary SQLite database (foreign keys enforced, like
PostgreSQL) and an in-memory fake worker client. No live deployment is touched.
"""
import hashlib
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db import models as M
from app.cluster.health_monitor import HealthMonitor
from app.repositories import chunk_repository as chunk_repo_module
from app.scheduler import replication as replication_module
from app.scheduler.replication import ReconcileResult, ReplicationManager
from app.services.worker_client import WorkerClient
from shared.exceptions import ChunkNotFoundError, WorkerUnavailableError
from shared.models import ChunkVerifyResult

RF = 2


# ---------------------------------------------------------------------------- fixtures
class FakeWorkers(WorkerClient):
    """In-memory stand-in for WorkerClient with fault injection (no network)."""

    def __init__(self):  # deliberately does not create the real HTTP client
        self.store: dict[tuple[str, str], bytes] = {}
        self.puts: list[tuple[str, str]] = []
        self.fail_put: set[str] = set()
        self.fail_get: set[str] = set()
        self.bad_write: set[str] = set()  # worker stores garbage (verification must catch it)
        self.put_delay = 0.0
        self.on_put = None  # optional hook(base_url, chunk_id)
        self.lock = threading.Lock()

    def put_chunk(self, base_url, chunk_id, data):
        if self.put_delay:
            time.sleep(self.put_delay)
        with self.lock:
            self.puts.append((base_url, chunk_id))
        if self.on_put:
            self.on_put(base_url, chunk_id)
        if base_url in self.fail_put:
            raise WorkerUnavailableError(f"PUT {chunk_id} -> {base_url}: connection refused")
        self.store[(base_url, chunk_id)] = b"garbage" if base_url in self.bad_write else bytes(data)

    def get_chunk(self, base_url, chunk_id):
        if base_url in self.fail_get:
            raise WorkerUnavailableError(f"GET {chunk_id} <- {base_url}: connection refused")
        if (base_url, chunk_id) not in self.store:
            raise ChunkNotFoundError(chunk_id)
        return self.store[(base_url, chunk_id)]

    def delete_chunk(self, base_url, chunk_id, timeout=None):
        del timeout  # accepted for interface compatibility with WorkerClient
        self.store.pop((base_url, chunk_id), None)

    def verify_chunk(self, base_url, chunk_id):
        b = self.store.get((base_url, chunk_id))
        if b is None or base_url in self.fail_get:
            return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
        return ChunkVerifyResult(chunk_id=chunk_id, exists=True, checksum=hashlib.sha256(b).hexdigest(), size_bytes=len(b))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'meta.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def url(w):
    return f"http://{w}:8001"


def seed(factory, fake, workers, chunks):
    """workers: {id: status}; chunks: {chunk_id: [(worker_id, replica_status), ...]} (one object per chunk)."""
    with factory() as db:
        for wid, status in workers.items():
            db.add(M.Worker(id=wid, base_url=url(wid), status=status, used_bytes=0,
                            last_heartbeat=datetime.now(timezone.utc)))
        db.commit()
        for cid, reps in chunks.items():
            oid = cid.rsplit("_", 1)[0]
            data = f"payload-of-{cid}".encode() * 100
            db.add(M.StoredObject(id=oid, name=f"{oid}.bin", size_bytes=len(data), checksum=hashlib.sha256(data).hexdigest(),
                                  chunk_count=1, status="available", custom_metadata={}))
            db.add(M.Chunk(id=cid, object_id=oid, chunk_index=0, size_bytes=len(data),
                           checksum=hashlib.sha256(data).hexdigest(), status="stored"))
            db.commit()
            for wid, rstatus in reps:
                db.add(M.ChunkReplica(chunk_id=cid, worker_id=wid, status=rstatus))
                fake.store[(url(wid), cid)] = data if rstatus == "stored" else b"rotten"
            db.commit()


def replicas(factory, cid):
    with factory() as db:
        return sorted((r.worker_id, r.status) for r in db.query(M.ChunkReplica).filter_by(chunk_id=cid))


def usable(factory, cid):
    with factory() as db:
        return sum(1 for r in db.query(M.ChunkReplica).filter_by(chunk_id=cid)
                   if r.status == "stored" and db.get(M.Worker, r.worker_id).status == "active")


def manager(factory, fake, clock=None, rf=RF):
    m = ReplicationManager(session_factory=factory, worker_client=fake, clock=clock or Clock())
    m.settings = Settings(replication_factor=rf, replication_retry_base_seconds=5, replication_retry_max_seconds=60)
    return m


FOUR = {"w1": "active", "w2": "active", "w3": "active", "w4": "active"}


# ---------------------------------------------------------------------------- 1
def test_detects_under_replicated_chunk(env):
    fake = FakeWorkers()
    workers = dict(FOUR, w2="unhealthy")
    seed(env, fake, workers, {
        "a_0": [("w1", "stored"), ("w2", "stored")],          # copy on unavailable worker -> 1 usable
        "b_0": [("w1", "stored"), ("w3", "corrupt")],         # corrupt copy not usable -> 1 usable
        "c_0": [("w1", "stored"), ("w3", "stored")],          # healthy
    })
    assert sorted(manager(env, fake).find_under_replicated()) == ["a_0", "b_0"]


# ---------------------------------------------------------------------------- 2
def test_successful_repair_restores_rf(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    res = manager(env, fake).reconcile_once()
    assert (res.under_replicated, res.restored, res.replicas_added, res.failed) == (1, 1, 1, 0)
    assert usable(env, "a_0") == RF
    new = [w for w, _ in replicas(env, "a_0") if w not in ("w1", "w2")]
    assert len(new) == 1 and fake.store[(url(new[0]), "a_0")] == fake.store[(url("w1"), "a_0")]


def test_respects_configured_replication_factor(env):
    fake = FakeWorkers()
    seed(env, fake, FOUR, {"a_0": [("w1", "stored")]})
    res = manager(env, fake, rf=3).reconcile_once()
    assert res.replicas_added == 2 and usable(env, "a_0") == 3


# ---------------------------------------------------------------------------- 3
def test_failed_repair_is_retried_on_a_later_cycle_with_backoff(env):
    fake = FakeWorkers()
    clock = Clock()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    fake.fail_put = {url("w3"), url("w4")}
    m = manager(env, fake, clock)

    r1 = m.reconcile_once()
    assert (r1.failed, r1.replicas_added) == (1, 0) and usable(env, "a_0") == 1
    puts_after_first = len(fake.puts)

    r2 = m.reconcile_once()                       # still inside backoff: no new attempts
    assert (r2.deferred, r2.attempted) == (1, 0) and len(fake.puts) == puts_after_first

    clock.t += 5.1                                # first backoff = base 5 s
    r3 = m.reconcile_once()                       # retried, still failing -> backoff doubles
    assert r3.attempted == 1 and r3.failed == 1
    clock.t += 5.1
    assert m.reconcile_once().deferred == 1       # 10 s backoff not yet elapsed

    fake.fail_put = set()                         # transient failure clears
    clock.t += 5.0
    r5 = m.reconcile_once()
    assert r5.restored == 1 and usable(env, "a_0") == RF


# ---------------------------------------------------------------------------- 4
def test_transient_db_error_does_not_block_other_chunks(env, monkeypatch):
    fake = FakeWorkers()
    clock = Clock()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {
        "a_0": [("w1", "stored"), ("w2", "stored")],
        "b_0": [("w1", "stored"), ("w2", "stored")],
    })
    original = chunk_repo_module.ChunkRepository.add_replica
    calls = {"n": 0}

    def flaky_add_replica(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("INSERT INTO chunk_replicas ...", {}, Exception("server closed the connection"))
        return original(self, *a, **k)

    monkeypatch.setattr(chunk_repo_module.ChunkRepository, "add_replica", flaky_add_replica)
    m = manager(env, fake, clock)
    res = m.reconcile_once()
    assert (res.attempted, res.restored, res.failed) == (2, 1, 1)
    failed = res.failed_chunks[0]
    # the copy written for the failed chunk was removed (no orphan without metadata)
    recorded = {w for w, _ in replicas(env, failed)}
    assert not [k for k in fake.store if k[1] == failed and k[0] not in {url(w) for w in recorded}]
    clock.t += 5.1
    assert m.reconcile_once().restored == 1
    assert usable(env, "a_0") == RF and usable(env, "b_0") == RF


# ---------------------------------------------------------------------------- 5
def test_failed_transaction_is_rolled_back_and_does_not_poison_later_work(env, monkeypatch):
    """Object deleted after the 'still wanted' check -> FK violation on insert.
    The session must be rolled back, the copy discarded, and the next chunk repaired."""
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {
        "a_0": [("w1", "stored"), ("w2", "stored")],
        "b_0": [("w1", "stored"), ("w2", "stored")],
    })
    real_check = ReplicationManager._chunk_still_wanted
    state = {"fired": False}

    def racy_check(db, chunk_id):
        ok = real_check(db, chunk_id)
        if chunk_id == "a_0" and ok and state["fired"] is False and fake.puts:
            state["fired"] = True
            with env() as other:  # concurrent DELETE commits right after our check
                other.query(M.ChunkReplica).filter_by(chunk_id="a_0").delete()
                other.query(M.Chunk).filter_by(id="a_0").delete()
                other.query(M.StoredObject).filter_by(id="a").delete()
                other.commit()
        return ok

    monkeypatch.setattr(ReplicationManager, "_chunk_still_wanted", staticmethod(racy_check))
    res = manager(env, fake).reconcile_once()
    assert state["fired"]
    assert "a_0" in res.failed_chunks           # FK violation surfaced as a failed repair, not a crash
    assert usable(env, "b_0") == RF             # the next chunk was repaired with a fresh session
    assert not [k for k in fake.store if k[1] == "a_0" and k[0] not in (url("w1"), url("w2"))]  # no orphan copy
    # the deleted chunk is simply gone from the work list on the next pass
    assert manager(env, fake).find_under_replicated() == []


def test_deletion_detected_before_recording_discards_copy(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})

    def delete_object_during_put(_base_url, _chunk_id):
        with env() as other:
            other.get(M.StoredObject, "a").status = "deleting"
            other.commit()

    fake.on_put = delete_object_during_put
    res = manager(env, fake).reconcile_once()
    assert res.failed == 0 and res.replicas_added == 0
    assert [k for k in fake.store if k[1] == "a_0"] == [(url("w1"), "a_0"), (url("w2"), "a_0")]


# ---------------------------------------------------------------------------- 6
def test_unavailable_target_falls_back_to_next_candidate(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    fake.fail_put = {url("w3")}
    res = manager(env, fake).reconcile_once()
    assert res.restored == 1 and ("w4", "stored") in replicas(env, "a_0")
    assert ("w3", "stored") not in replicas(env, "a_0")


def test_unreadable_source_uses_another_source(env):
    fake = FakeWorkers()
    seed(env, fake, FOUR, {"a_0": [("w1", "stored"), ("w2", "stored")]})
    m = manager(env, fake, rf=3)
    fake.fail_get = {url("w1")}
    assert m.reconcile_once().restored == 1 and usable(env, "a_0") == 3


def test_copy_failing_verification_is_not_recorded(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    fake.bad_write = {url("w3")}
    res = manager(env, fake).reconcile_once()
    assert res.restored == 1
    reps = dict(replicas(env, "a_0"))
    assert "w3" not in reps and reps.get("w4") == "stored"
    assert (url("w3"), "a_0") not in fake.store        # bad copy discarded


def test_no_target_available_is_reported_and_retried(env):
    fake = FakeWorkers()
    clock = Clock()
    seed(env, fake, {"w1": "active", "w2": "unhealthy"}, {"a_0": [("w1", "stored"), ("w2", "stored")]})
    m = manager(env, fake, clock)
    assert m.reconcile_once().failed == 1
    with env() as db:  # capacity returns: a new worker registers
        db.add(M.Worker(id="w5", base_url=url("w5"), status="active", used_bytes=0))
        db.commit()
    clock.t += 5.1
    assert m.reconcile_once().restored == 1 and ("w5", "stored") in replicas(env, "a_0")


# ---------------------------------------------------------------------------- 7
def test_restart_resumes_from_persistent_metadata(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    fake.fail_put = {url("w3"), url("w4")}
    first = manager(env, fake)
    assert first.reconcile_once().failed == 1     # leaves backoff state in memory only
    fake.fail_put = set()
    restarted = manager(env, fake)                # new controller process: fresh memory, same DB
    assert restarted.reconcile_once().restored == 1 and usable(env, "a_0") == RF


# ---------------------------------------------------------------------------- 8
def test_no_duplicate_replicas_over_repeated_cycles(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    m = manager(env, fake)
    m.reconcile_once()
    rows_after_repair = replicas(env, "a_0")
    puts_after_repair = len(fake.puts)
    for _ in range(3):
        m.reconcile_once()
    assert replicas(env, "a_0") == rows_after_repair
    assert len(fake.puts) == puts_after_repair
    workers = [w for w, _ in rows_after_repair]
    assert len(workers) == len(set(workers)) == 3  # w1, w2 (unhealthy, kept), one new


# ---------------------------------------------------------------------------- 9
def test_healthy_and_over_replicated_chunks_are_untouched(env):
    fake = FakeWorkers()
    seed(env, fake, FOUR, {
        "a_0": [("w1", "stored"), ("w2", "stored")],
        "b_0": [("w1", "stored"), ("w2", "stored"), ("w3", "stored")],  # excess copies are NOT trimmed here
    })
    before = (replicas(env, "a_0"), replicas(env, "b_0"))
    res = manager(env, fake).reconcile_once()
    assert (res.under_replicated, res.attempted) == (0, 0) and fake.puts == []
    assert (replicas(env, "a_0"), replicas(env, "b_0")) == before


# ---------------------------------------------------------------------------- 10
def test_concurrent_reconciliation_does_not_duplicate(env):
    fake = FakeWorkers()
    seed(env, fake, dict(FOUR, w2="unhealthy"), {"a_0": [("w1", "stored"), ("w2", "stored")]})
    fake.put_delay = 0.3
    managers = [manager(env, fake), manager(env, fake)]  # e.g. a monitor tick and a manual trigger
    barrier = threading.Barrier(2)
    results = []

    def run(m):
        barrier.wait()
        results.append(m.reconcile_once())

    threads = [threading.Thread(target=run, args=(m,)) for m in managers]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r.skipped_busy for r in results) == [False, True]
    assert len(fake.puts) == 1 and usable(env, "a_0") == RF
    assert len(replicas(env, "a_0")) == 3


# ---------------------------------------------------------------------------- monitor wiring
class _CountingReplication(ReplicationManager):
    """Stub that only counts reconciliation passes (no DB, no HTTP client)."""

    def __init__(self, fail=False):  # deliberately does not call ReplicationManager.__init__
        self.calls = 0
        self.fail = fail

    def reconcile_once(self) -> ReconcileResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return ReconcileResult()


def test_monitor_reconciles_without_any_health_transition(env, monkeypatch):
    rep = _CountingReplication()
    mon = HealthMonitor(session_factory=env, replication_manager=rep)
    mon.settings = Settings(replication_reconcile_interval_seconds=10)
    t = {"now": 100.0}
    monkeypatch.setattr("app.cluster.health_monitor.time.monotonic", lambda: t["now"])
    mon.check_once()                      # first tick after start-up: reconcile immediately
    t["now"] += 5
    mon.check_once()                      # not yet due
    t["now"] += 6
    mon.check_once()                      # due again, although no worker changed state
    assert rep.calls == 2


def test_monitor_survives_reconciliation_errors(env):
    rep = _CountingReplication(fail=True)
    mon = HealthMonitor(session_factory=env, replication_manager=rep)
    mon.check_once()                      # must not raise
    assert rep.calls == 1


def test_reconcile_survives_metadata_read_failure(env, monkeypatch):
    fake = FakeWorkers()
    m = manager(env, fake)
    monkeypatch.setattr(m, "find_under_replicated", lambda: (_ for _ in ()).throw(OperationalError("SELECT", {}, Exception("db down"))))
    res = m.reconcile_once()              # logged, no exception, lock released
    assert res.attempted == 0
    assert replication_module._RECONCILE_LOCK.acquire(blocking=False)
    replication_module._RECONCILE_LOCK.release()
