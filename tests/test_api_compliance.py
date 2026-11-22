"""Tests for API compliance: JSON error responses, pagination, MIME detection, Unicode headers."""
import io
import os
import tempfile
from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import install_exception_handlers
from client.client import CloudWeaveClient

CONTROLLER_URL = os.environ.get("CLOUDWEAVE_URL", "http://localhost:8000")


# ==============================================================================
# 1 & 2 & 3: Error responses and pagination
# ==============================================================================
def test_unhandled_internal_error_returns_json():
    """Unexpected 500 error returns structured JSON."""
    test_app = FastAPI()
    install_exception_handlers(test_app)

    @test_app.get("/trigger-500")
    def trigger_500():
        raise RuntimeError("Unexpected simulated internal crash")

    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/trigger-500")
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    data = resp.json()
    assert data == {"detail": "Internal server error"}


def test_invalid_pagination_offset_negative():
    """Negative offset returns 400 JSON error."""
    resp = httpx.get(f"{CONTROLLER_URL}/api/v1/objects?offset=-1")
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "offset must be greater than or equal to 0"}


def test_invalid_pagination_limit_zero():
    """Limit < 1 returns 400 JSON error."""
    resp = httpx.get(f"{CONTROLLER_URL}/api/v1/objects?limit=0")
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "limit must be between 1 and 1000"}


def test_invalid_pagination_limit_exceeds_1000():
    """Limit > 1000 returns 400 JSON error."""
    resp = httpx.get(f"{CONTROLLER_URL}/api/v1/objects?limit=1001")
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "limit must be between 1 and 1000"}


def test_missing_object_404_message():
    """Missing object returns 404 with 'Object {id} not found' message."""
    test_id = "nonexistent-test-uuid-9999"
    resp = httpx.get(f"{CONTROLLER_URL}/api/v1/objects/{test_id}")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": f"Object {test_id} not found"}


# ==============================================================================
# 4 & 5: MIME type detection
# ==============================================================================
def test_mime_type_detection_txt_and_unknown():
    """Test that .txt is detected as text/plain and unknown extension falls back to octet-stream."""
    client = CloudWeaveClient(base_url=CONTROLLER_URL)
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Text file
        txt_file = Path(tmp) / "sample_compliance.txt"
        txt_file.write_text("Plain text content")
        txt_res = client.upload(txt_file)
        txt_id = txt_res["id"]

        try:
            txt_meta = client.metadata(txt_id)
            assert txt_meta["content_type"] == "text/plain"

            # Check download header Content-Type
            r = httpx.get(f"{CONTROLLER_URL}/api/v1/objects/{txt_id}")
            assert r.headers["content-type"].startswith("text/plain")
        finally:
            client.delete(txt_id)

        # 2. Unknown binary file extension
        unk_file = Path(tmp) / "sample_data.custombinaryxyz"
        unk_file.write_bytes(b"\x00\x01\x02\x03\x04")
        unk_res = client.upload(unk_file)
        unk_id = unk_res["id"]

        try:
            unk_meta = client.metadata(unk_id)
            assert unk_meta["content_type"] == "application/octet-stream"

            r2 = httpx.get(f"{CONTROLLER_URL}/api/v1/objects/{unk_id}")
            assert r2.headers["content-type"].startswith("application/octet-stream")
        finally:
            client.delete(unk_id)

    client.close()


# ==============================================================================
# 6 & 7 & 8: Unicode and ASCII filenames, Content-Disposition headers
# ==============================================================================
def test_ascii_and_unicode_filename_downloads():
    """Test ASCII and Unicode filename downloads without HTTP 500, with correct Content-Disposition."""
    client = CloudWeaveClient(base_url=CONTROLLER_URL)
    with tempfile.TemporaryDirectory() as tmp:
        # 1. ASCII filename
        ascii_file = Path(tmp) / "regular_ascii_file.bin"
        ascii_bytes = b"ASCII test payload bytes 12345"
        ascii_file.write_bytes(ascii_bytes)
        ascii_res = client.upload(ascii_file)
        ascii_id = ascii_res["id"]

        try:
            dest_ascii = Path(tmp) / "download_dir_ascii"
            dest_ascii.mkdir()
            dl_ascii = client.download(ascii_id, destination=dest_ascii)
            assert dl_ascii == ascii_bytes
            assert (dest_ascii / "regular_ascii_file.bin").exists()

            # Inspect Content-Disposition
            r_ascii = httpx.get(f"{CONTROLLER_URL}/api/v1/objects/{ascii_id}")
            assert r_ascii.status_code == 200
            cd = r_ascii.headers["content-disposition"]
            assert 'filename="regular_ascii_file.bin"' in cd
        finally:
            client.delete(ascii_id)

        # 2. Unicode filename with accents, non-Latin, and spaces
        unicode_name = "rapport_résumé_తెలుగు_你好.txt"
        unicode_file = Path(tmp) / unicode_name
        unicode_bytes = "Unicode file content: வணக்கம், Здравствуйте, Hello!".encode("utf-8")
        unicode_file.write_bytes(unicode_bytes)
        unicode_res = client.upload(unicode_file)
        unicode_id = unicode_res["id"]

        try:
            dest_uni = Path(tmp) / "download_dir_uni"
            dest_uni.mkdir()
            dl_uni = client.download(unicode_id, destination=dest_uni)
            assert dl_uni == unicode_bytes
            # Client correctly recovered the original Unicode filename using filename*=UTF-8''
            assert (dest_uni / unicode_name).exists()
            assert (dest_uni / unicode_name).read_bytes() == unicode_bytes

            # Inspect Content-Disposition directly
            r_uni = httpx.get(f"{CONTROLLER_URL}/api/v1/objects/{unicode_id}")
            assert r_uni.status_code == 200
            cd_uni = r_uni.headers["content-disposition"]
            # Must have safe ASCII fallback
            assert 'filename="' in cd_uni
            # Must have UTF-8 encoded parameter
            assert "filename*=UTF-8''" in cd_uni
        finally:
            client.delete(unicode_id)

    client.close()
