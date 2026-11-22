"""
End-to-End API Integration Tests.
Tests full client-controller workflow against a live cluster:
cluster status, upload, download roundtrip, metadata querying,
in-place metadata patching, and cascading deletion.
"""
import os
import tempfile
import unittest
from pathlib import Path

from client.client import CloudWeaveClient

CONTROLLER_URL = os.environ.get("CLOUDWEAVE_URL", "http://localhost:8000")


class TestAPIIntegration(unittest.TestCase):
    """Integration test suite executing requests against the running CloudWeave cluster."""

    def setUp(self):
        """Initialize client connection before each test."""
        self.client = CloudWeaveClient(base_url=CONTROLLER_URL)

    def tearDown(self):
        """Close client connection after each test."""
        self.client.close()

    def test_cluster_status(self):
        """Verify cluster reports active workers and configured replication factor."""
        status = self.client.cluster_status()
        self.assertIn("workers", status)
        self.assertGreaterEqual(len(status["workers"]), 4)
        self.assertEqual(status["replication_factor"], 2)

    def test_upload_download_roundtrip(self):
        """Test full object lifecycle: upload, download, metadata patch, and delete."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roundtrip.bin"
            data = b"Hello, CloudWeave Distributed Object Store!\x00\xff\xfe"
            path.write_bytes(data)

            # 1. Upload file with initial metadata
            res = self.client.upload(path, metadata={"test_key": "test_val"})
            object_id = res["id"]
            self.assertEqual(res["size_bytes"], len(data))
            self.assertEqual(res["status"], "available")

            # 2. Download and verify binary byte-for-byte match
            dest = Path(tmp) / "downloaded.bin"
            downloaded = self.client.download(object_id, destination=dest)
            self.assertEqual(downloaded, data)
            self.assertEqual(dest.read_bytes(), data)

            # 3. Retrieve and inspect metadata
            meta = self.client.metadata(object_id)
            self.assertEqual(meta["custom_metadata"]["test_key"], "test_val")

            # 4. Patch metadata in-place without touching chunk data
            patched = self.client.patch_metadata(object_id, {"test_key": "updated_val", "new_key": "123"})
            self.assertEqual(patched["custom_metadata"]["test_key"], "updated_val")
            self.assertEqual(patched["custom_metadata"]["new_key"], "123")

            # 5. Delete object and confirm cascading cleanup
            self.assertTrue(self.client.delete(object_id))

            # 6. Verify subsequent download attempts raise 404
            with self.assertRaises(Exception):
                self.client.download(object_id)


if __name__ == "__main__":
    unittest.main()
