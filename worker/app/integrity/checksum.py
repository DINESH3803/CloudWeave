"""
Worker Checksum Utilities.
Calculates SHA-256 hashes for verifying chunk data integrity on local storage.
"""
import hashlib


def sha256_hex(data: bytes) -> str:
    """Compute hex-encoded SHA-256 hash of byte data."""
    return hashlib.sha256(data).hexdigest()
