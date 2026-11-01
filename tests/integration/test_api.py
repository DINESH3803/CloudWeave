"""Integration tests for CloudWeave Client REST API."""
import os
import tempfile
import unittest
from pathlib import Path

from client.client import CloudWeaveClient

CONTROLLER_URL = os.environ.get("CLOUDWEAVE_URL", "http://localhost:8000")


class TestAPIIntegration(unittest.TestCase):
    def setUp(self):
        self.client = CloudWeaveClient(base_url=CONTROLLER_URL)

    def tearDown(self):
        self.client.close()

    def test_cluster_status(self):
        status = self.client.cluster_status()
        self.assertIn("workers", status)
        self.assertGreaterEqual(len(status["workers"]), 4)
        self.assertEqual(status["replication_factor"], 2)

    def test_upload_download_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roundtrip.bin"
            data = b"Hello, CloudWeave Distributed Object Store!\x00\xff\xfe"
            path.write_bytes(data)

            # Upload
            res = self.client.upload(path, metadata={"test_key": "test_val"})
            object_id = res["id"]
            self.assertEqual(res["size_bytes"], len(data))
            self.assertEqual(res["status"], "available")

            # Download
            dest = Path(tmp) / "downloaded.bin"
            downloaded = self.client.download(object_id, destination=dest)
            self.assertEqual(downloaded, data)
            self.assertEqual(dest.read_bytes(), data)

            # Check metadata
            meta = self.client.metadata(object_id)
            self.assertEqual(meta["custom_metadata"]["test_key"], "test_val")

            # Patch metadata
            patched = self.client.patch_metadata(object_id, {"test_key": "updated_val", "new_key": "123"})
            self.assertEqual(patched["custom_metadata"]["test_key"], "updated_val")
            self.assertEqual(patched["custom_metadata"]["new_key"], "123")

            # Delete
            self.assertTrue(self.client.delete(object_id))

            # Verify 404 after delete
            with self.assertRaises(Exception):
                self.client.download(object_id)


if __name__ == "__main__":
    unittest.main()
