"""
Checksum Utilities.

Provides SHA-256 calculation helpers for raw byte blocks and streaming data.
"""
import hashlib
from collections.abc import Iterable


def sha256_hex(data: bytes) -> str:
    """Calculate hex-encoded SHA-256 checksum for a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_hex_stream(blocks: Iterable[bytes]) -> str:
    """
    Calculate composite SHA-256 checksum for a stream of byte chunks.
    
    Feeds each block sequentially into the hash digest.
    """
    digest = hashlib.sha256()
    for block in blocks:
        digest.update(block)
    return digest.hexdigest()


def matches(data: bytes, expected_checksum: str) -> bool:
    """Verify whether byte data matches an expected hex checksum."""
    return sha256_hex(data) == expected_checksum
