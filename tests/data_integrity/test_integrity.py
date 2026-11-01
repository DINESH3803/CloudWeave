"""Unit and integrity tests for chunking and hashing."""
import io
import hashlib
import unittest

from controller.app.services.chunk_service import split_into_chunks
from controller.app.integrity.checksum import sha256_hex, sha256_hex_stream, matches


class TestDataIntegrity(unittest.TestCase):
    def test_sha256_checksum(self):
        data = b"Testing checksum verification"
        expected = hashlib.sha256(data).hexdigest()
        self.assertEqual(sha256_hex(data), expected)
        self.assertTrue(matches(data, expected))
        self.assertFalse(matches(data, "wrong_hash"))

    def test_chunking_stream(self):
        # 2.5 MB data
        total_len = int(2.5 * 1024 * 1024)
        data = b"X" * total_len
        stream = io.BytesIO(data)

        chunks = list(split_into_chunks(stream, 1024 * 1024))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 1024 * 1024)
        self.assertEqual(len(chunks[1]), 1024 * 1024)
        self.assertEqual(len(chunks[2]), 512 * 1024)

        reassembled = b"".join(chunks)
        self.assertEqual(reassembled, data)
        self.assertEqual(sha256_hex_stream(chunks), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
