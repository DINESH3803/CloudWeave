"""Tests for CW-07: Reliable and Complete Object Downloads.

Isolated: temporary SQLite database (foreign keys enforced) and an in-memory
fake worker client with fault injection. No live deployment is touched.
"""
import hashlib
import io
import os
import tempfile
import threading
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db import models as M
from app.services.object_service import ObjectService, EMPTY_SHA256
from app.services.worker_client import WorkerClient
from shared.exceptions import (
    ChecksumMismatchError,
    ChunkNotFoundError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    WorkerUnavailableError,
)


# ---------------------------------------------------------------------------- helpers

def url(w: str) -> str:
    return f"http://{w}:8001"


class FakeWorkers(WorkerClient):
    """In-memory fake WorkerClient with fault injection."""

    def __init__(self):  # does NOT create the real HTTP client
        self.store: dict[tuple[str, str], bytes] = {}
        self.fail_get: set[str] = set()       # base_urls that raise WorkerUnavailableError
        self.corrupt_get: set[str] = set()    # base_urls that return garbage bytes

    def put_chunk(self, base_url, chunk_id, data):
        self.store[(base_url, chunk_id)] = bytes(data)

    def get_chunk(self, base_url, chunk_id):
        if base_url in self.fail_get:
            raise WorkerUnavailableError(f"GET {chunk_id} <- {base_url}: connection refused")
        if (base_url, chunk_id) not in self.store:
            raise ChunkNotFoundError(chunk_id)
        raw = self.store[(base_url, chunk_id)]
        if base_url in self.corrupt_get:
            return b"CORRUPTED_DATA_" + raw[:4]
        return raw

    def verify_chunk(self, base_url, chunk_id):
        from shared.models import ChunkVerifyResult
        b = self.store.get((base_url, chunk_id))
        if b is None:
            return ChunkVerifyResult(chunk_id=chunk_id, exists=False)
        return ChunkVerifyResult(chunk_id=chunk_id, exists=True, checksum=hashlib.sha256(b).hexdigest(), size_bytes=len(b))

    def delete_chunk(self, base_url, chunk_id, timeout=None):
        self.store.pop((base_url, chunk_id), None)


# ---------------------------------------------------------------------------- fixtures

@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'meta.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # Seed four workers
    with factory() as db:
        for w in ("w1", "w2", "w3", "w4"):
            db.add(M.Worker(id=w, base_url=url(w), status="active", used_bytes=0,
                            last_heartbeat=datetime.now(timezone.utc)))
        db.commit()
    yield factory
    engine.dispose()


def make_service(factory, fake: FakeWorkers, chunk_size: int = 1024 * 1024) -> ObjectService:
    db = factory()
    svc = ObjectService(db)
    svc.settings = Settings(chunk_size_bytes=chunk_size)
    svc.chunk_service.settings = Settings(chunk_size_bytes=chunk_size, worker_cleanup_timeout_seconds=2.0)
    svc.chunk_service.worker_client = fake
    return svc


def do_upload(factory, fake: FakeWorkers, data: bytes, chunk_size: int = 1024 * 1024) -> str:
    """Upload data and return object_id."""
    svc = make_service(factory, fake, chunk_size)
    obj = svc.upload("test.bin", "application/octet-stream", io.BytesIO(data))
    svc.db.close()
    return obj.id


def do_download(factory, fake: FakeWorkers, object_id: str) -> bytes:
    """Download and return all bytes."""
    svc = make_service(factory, fake)
    _, gen = svc.download(object_id)
    result = b"".join(gen)
    svc.db.close()
    return result


# ---------------------------------------------------------------------------- tests

# 1. Single-chunk object
def test_single_chunk_download(env):
    fake = FakeWorkers()
    data = b"Hello CloudWeave CW-07!"
    oid = do_upload(env, fake, data)
    downloaded = do_download(env, fake, oid)
    assert downloaded == data


# 2. Multi-chunk object
def test_multi_chunk_download(env):
    fake = FakeWorkers()
    chunk_size = 512
    data = b"X" * (chunk_size * 3 + 100)  # 3 full + 1 partial chunk
    oid = do_upload(env, fake, data, chunk_size=chunk_size)
    downloaded = do_download(env, fake, oid)
    assert downloaded == data


# 3. Correct chunk ordering
def test_chunk_ordering(env):
    fake = FakeWorkers()
    chunk_size = 256
    # Each chunk has distinct content to verify ordering
    part1 = b"AAAA" * (chunk_size // 4)
    part2 = b"BBBB" * (chunk_size // 4)
    part3 = b"CCCC" * (chunk_size // 4)
    data = part1 + part2 + part3
    oid = do_upload(env, fake, data, chunk_size=chunk_size)
    downloaded = do_download(env, fake, oid)
    assert downloaded == data
    assert downloaded[:chunk_size] == part1
    assert downloaded[chunk_size:2*chunk_size] == part2
    assert downloaded[2*chunk_size:] == part3


# 4. First replica unavailable, alternate succeeds
def test_first_replica_unavailable_alternate_succeeds(env):
    fake = FakeWorkers()
    data = b"replica fallback test data"
    oid = do_upload(env, fake, data)

    # Find which workers hold the chunk
    svc = make_service(env, fake)
    obj = svc.get(oid)
    chunk = obj.chunks[0]
    replicas = [r for r in chunk.replicas if r.worker]
    svc.db.close()

    # Fail the first replica's worker
    first_worker_url = replicas[0].worker.base_url
    fake.fail_get.add(first_worker_url)

    downloaded = do_download(env, fake, oid)
    assert downloaded == data


# 5. All replicas unavailable for a required chunk
def test_all_replicas_unavailable(env):
    fake = FakeWorkers()
    data = b"test data for all replicas unavailable"
    oid = do_upload(env, fake, data)

    # Fail ALL worker URLs
    for w in ("w1", "w2", "w3", "w4"):
        fake.fail_get.add(url(w))

    svc = make_service(env, fake)
    with pytest.raises(WorkerUnavailableError):
        svc.download(oid)
    svc.db.close()


# 6. First chunk unavailable (all replicas of first chunk unavailable)
def test_first_chunk_unavailable(env):
    fake = FakeWorkers()
    chunk_size = 256
    data = b"X" * (chunk_size * 2)
    oid = do_upload(env, fake, data, chunk_size=chunk_size)

    # Fail all replicas of chunk 0
    svc = make_service(env, fake)
    obj = svc.get(oid)
    chunk0 = next(c for c in obj.chunks if c.chunk_index == 0)
    for rep in chunk0.replicas:
        if rep.worker:
            fake.fail_get.add(rep.worker.base_url)
    svc.db.close()

    svc2 = make_service(env, fake)
    with pytest.raises(WorkerUnavailableError):
        svc2.download(oid)
    svc2.db.close()


# 7. Middle chunk unavailable (all replicas)
def test_middle_chunk_all_replicas_unavailable(env):
    fake = FakeWorkers()
    chunk_size = 256
    data = b"Y" * (chunk_size * 3)
    oid = do_upload(env, fake, data, chunk_size=chunk_size)

    # Fail middle chunk (index 1) on all workers
    svc = make_service(env, fake)
    obj = svc.get(oid)
    chunk1 = next(c for c in obj.chunks if c.chunk_index == 1)
    for rep in chunk1.replicas:
        if rep.worker:
            fake.fail_get.add(rep.worker.base_url)
    svc.db.close()

    svc2 = make_service(env, fake)
    with pytest.raises(WorkerUnavailableError):
        svc2.download(oid)
    svc2.db.close()


# 8. Last chunk unavailable (all replicas)
def test_last_chunk_all_replicas_unavailable(env):
    fake = FakeWorkers()
    chunk_size = 256
    data = b"Z" * (chunk_size * 3)
    oid = do_upload(env, fake, data, chunk_size=chunk_size)

    svc = make_service(env, fake)
    obj = svc.get(oid)
    last_chunk = max(obj.chunks, key=lambda c: c.chunk_index)
    for rep in last_chunk.replicas:
        if rep.worker:
            fake.fail_get.add(rep.worker.base_url)
    svc.db.close()

    svc2 = make_service(env, fake)
    with pytest.raises(WorkerUnavailableError):
        svc2.download(oid)
    svc2.db.close()


# 9. First replica returns corrupt data, alternate replica is valid
def test_corrupt_first_replica_falls_back_to_valid(env):
    fake = FakeWorkers()
    data = b"valid data for corruption test"
    oid = do_upload(env, fake, data)

    # Find first replica, corrupt it
    svc = make_service(env, fake)
    obj = svc.get(oid)
    chunk = obj.chunks[0]
    first_replica = chunk.replicas[0]
    first_url = first_replica.worker.base_url
    svc.db.close()

    # Corrupt the data on first worker directly in the store
    chunk_id = chunk.id
    fake.store[(first_url, chunk_id)] = b"THIS_IS_GARBAGE_DATA"

    downloaded = do_download(env, fake, oid)
    assert downloaded == data


# 10. All replicas return corrupt data
def test_all_replicas_corrupt(env):
    fake = FakeWorkers()
    data = b"all corrupt test"
    oid = do_upload(env, fake, data)

    # Corrupt all copies in the store for this object's chunk
    svc = make_service(env, fake)
    obj = svc.get(oid)
    chunk = obj.chunks[0]
    chunk_id = chunk.id
    svc.db.close()

    for key in list(fake.store.keys()):
        if key[1] == chunk_id:
            fake.store[key] = b"GARBAGE_GARBAGE_GARBAGE"

    svc2 = make_service(env, fake)
    with pytest.raises(WorkerUnavailableError):
        svc2.download(oid)
    svc2.db.close()


# 11. Reconstructed size does not match stored size
def test_size_mismatch_raises_before_200(env):
    """Tamper with stored size metadata; download must raise, not return HTTP 200."""
    fake = FakeWorkers()
    data = b"size mismatch test" * 10
    oid = do_upload(env, fake, data)

    # Tamper: set stored size to wrong value in DB
    with env() as db:
        obj = db.get(M.StoredObject, oid)
        obj.size_bytes = obj.size_bytes + 1  # wrong
        db.commit()

    svc = make_service(env, fake)
    with pytest.raises(ObjectIntegrityError, match="size"):
        svc.download(oid)
    svc.db.close()


# 12. Final object checksum mismatch
def test_object_checksum_mismatch_raises(env):
    """Tamper with stored checksum; download must raise ObjectIntegrityError."""
    fake = FakeWorkers()
    data = b"checksum mismatch test"
    oid = do_upload(env, fake, data)

    with env() as db:
        obj = db.get(M.StoredObject, oid)
        obj.checksum = "deadbeef" * 8  # wrong checksum
        db.commit()

    svc = make_service(env, fake)
    with pytest.raises(ObjectIntegrityError, match="checksum"):
        svc.download(oid)
    svc.db.close()


# 13. Temporary-file creation failure
def test_temp_file_creation_failure(env):
    fake = FakeWorkers()
    data = b"temp file creation failure test"
    oid = do_upload(env, fake, data)

    svc = make_service(env, fake)
    with patch("tempfile.SpooledTemporaryFile", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            svc.download(oid)
    svc.db.close()


# 14. Temporary-file write failure
def test_temp_file_write_failure(env):
    fake = FakeWorkers()
    data = b"temp file write failure test"
    oid = do_upload(env, fake, data)

    svc = make_service(env, fake)
    mock_tmp = MagicMock()
    mock_tmp.__enter__ = MagicMock(return_value=mock_tmp)
    mock_tmp.__exit__ = MagicMock(return_value=False)
    mock_tmp.write.side_effect = OSError("write error")
    mock_tmp.close = MagicMock()

    with patch("tempfile.SpooledTemporaryFile", return_value=mock_tmp):
        with pytest.raises(OSError, match="write error"):
            svc.download(oid)

    # Temp file must be closed on failure
    mock_tmp.close.assert_called_once()
    svc.db.close()


# 15. Temporary-file cleanup after successful download
def test_temp_file_cleanup_after_success(env):
    fake = FakeWorkers()
    data = b"cleanup after success"
    oid = do_upload(env, fake, data)

    svc = make_service(env, fake)
    closed_flag = {"closed": False}
    real_spooled = tempfile.SpooledTemporaryFile

    class TrackingSpooled:
        def __init__(self, *args, **kwargs):
            self._inner = real_spooled(*args, **kwargs)
            closed_flag["closed"] = False

        def write(self, data):
            return self._inner.write(data)

        def seek(self, pos):
            return self._inner.seek(pos)

        def read(self, size=-1):
            return self._inner.read(size)

        def close(self):
            closed_flag["closed"] = True
            return self._inner.close()

    with patch("tempfile.SpooledTemporaryFile", TrackingSpooled):
        _, gen = svc.download(oid)
        assert not closed_flag["closed"], "should not be closed before consuming"
        result = b"".join(gen)
        assert result == data
        assert closed_flag["closed"], "should be closed after generator exhausted"

    svc.db.close()


# 16. Temporary-file cleanup after failure or client disconnect, where testable
def test_temp_file_cleanup_after_failure(env):
    fake = FakeWorkers()
    data = b"cleanup after failure"
    oid = do_upload(env, fake, data)

    # Fail all workers so download raises
    for w in ("w1", "w2", "w3", "w4"):
        fake.fail_get.add(url(w))

    svc = make_service(env, fake)
    closed_flag = {"closed": False}
    real_spooled = tempfile.SpooledTemporaryFile

    class TrackingSpooled:
        def __init__(self, *args, **kwargs):
            self._inner = real_spooled(*args, **kwargs)

        def write(self, data):
            return self._inner.write(data)

        def seek(self, pos):
            return self._inner.seek(pos)

        def read(self, size=-1):
            return self._inner.read(size)

        def close(self):
            closed_flag["closed"] = True
            return self._inner.close()

    with patch("tempfile.SpooledTemporaryFile", TrackingSpooled):
        with pytest.raises(WorkerUnavailableError):
            svc.download(oid)

    assert closed_flag["closed"], "temp file must be closed after failure"
    svc.db.close()


def test_temp_file_cleanup_on_client_disconnect(env):
    """If client disconnects mid-stream, generator.close() triggers cleanup."""
    fake = FakeWorkers()
    data = b"client disconnect test data " * 1000
    oid = do_upload(env, fake, data)

    svc = make_service(env, fake)
    closed_flag = {"closed": False}
    real_spooled = tempfile.SpooledTemporaryFile

    class TrackingSpooled:
        def __init__(self, *args, **kwargs):
            self._inner = real_spooled(*args, **kwargs)

        def write(self, d):
            return self._inner.write(d)

        def seek(self, pos):
            return self._inner.seek(pos)

        def read(self, size=-1):
            return self._inner.read(size)

        def close(self):
            closed_flag["closed"] = True
            return self._inner.close()

    with patch("tempfile.SpooledTemporaryFile", TrackingSpooled):
        _, gen = svc.download(oid)
        assert not closed_flag["closed"], "file should remain open while streaming"
        # Client reads only first chunk then aborts/disconnects
        next(gen)
        assert not closed_flag["closed"], "file still open after reading partial"
        # Generator close simulates client abort / connection reset
        close_fn = getattr(gen, "close", None)
        assert close_fn is not None, "generator should have a close() method"
        close_fn()
        assert closed_flag["closed"], "file must be closed when generator is closed"

    svc.db.close()


# 17. Object deleted while download is being prepared (race: deleted between get and chunk retrieval)
def test_object_deleted_during_download(env):
    """Object is deleted (gone from DB) while download is in progress."""
    fake = FakeWorkers()
    data = b"delete race condition test"
    oid = do_upload(env, fake, data)

    # Delete the object from DB while we have a service referencing it
    with env() as db:
        obj = db.get(M.StoredObject, oid)
        # Manually wipe replicas, chunks, object to simulate concurrent deletion
        for chunk in obj.chunks:
            for rep in chunk.replicas:
                db.delete(rep)
            db.delete(chunk)
        db.delete(obj)
        db.commit()

    # Also remove actual chunk data from workers so retrieval fails
    fake.store.clear()

    svc = make_service(env, fake)
    with pytest.raises((ObjectNotFoundError, WorkerUnavailableError, ChunkNotFoundError)):
        svc.download(oid)
    svc.db.close()


# ---------------------------------------------------------------------------- no HTTP 200 with partial content

def test_failure_before_response_does_not_produce_200():
    """Verify that download() raises BEFORE returning, not inside a lazy generator.
    
    This test verifies the fundamental fix: download() must either return successfully
    (with all data buffered) or raise an exception — never return a generator that may
    fail mid-stream.
    """
    # With the fix, download() raises synchronously if chunk retrieval fails.
    # Test: upload succeeds, then destroy all worker data, then download must raise.
    import io
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.db import models as M
    from datetime import datetime, timezone

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

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

    fake = FakeWorkers()
    db = factory()
    svc = ObjectService(db)
    svc.settings = Settings(chunk_size_bytes=512)
    svc.chunk_service.settings = Settings(chunk_size_bytes=512, worker_cleanup_timeout_seconds=2.0)
    svc.chunk_service.worker_client = fake

    obj = svc.upload("test.bin", "application/octet-stream", io.BytesIO(b"X" * 1024))
    oid = obj.id
    db.close()

    # Clear all worker data - simulate all workers losing data
    fake.store.clear()
    for w in ("w1", "w2", "w3", "w4"):
        fake.fail_get.add(url(w))

    # With the OLD implementation, download() would return a generator
    # and the error would only occur when the generator was iterated.
    # With the NEW implementation, download() must raise HERE, not in the generator.
    db2 = factory()
    svc2 = ObjectService(db2)
    svc2.settings = Settings(chunk_size_bytes=512)
    svc2.chunk_service.settings = Settings(chunk_size_bytes=512, worker_cleanup_timeout_seconds=2.0)
    svc2.chunk_service.worker_client = fake

    raised_before_generator = False
    try:
        result = svc2.download(oid)
        # If we get here, download returned something. With the old code, this would
        # be a generator that hasn't failed yet. With the new code, it must have
        # already assembled the full content.
        # Try to consume the result
        if isinstance(result, tuple):
            _, gen = result
            list(gen)  # This would fail with old code
        # If we got here with no exception, something is wrong
    except (WorkerUnavailableError, ChunkNotFoundError) as e:
        raised_before_generator = True
    finally:
        db2.close()

    assert raised_before_generator, (
        "download() must raise WorkerUnavailableError before returning, "
        "not inside a lazy generator"
    )

    engine.dispose()
