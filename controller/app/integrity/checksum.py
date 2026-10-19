"""Checksum utilities (SHA-256)."""
import hashlib
from collections.abc import Iterable


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_stream(blocks: Iterable[bytes]) -> str:
    """Hash data supplied incrementally, e.g. a whole object chunk by chunk."""
    digest = hashlib.sha256()
    for block in blocks:
        digest.update(block)
    return digest.hexdigest()


def matches(data: bytes, expected_checksum: str) -> bool:
    return sha256_hex(data) == expected_checksum
