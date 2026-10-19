"""Chunk placement: decide which workers receive each chunk's replicas."""
from typing import Protocol

from shared.models import WorkerInfo


class PlacementStrategy(Protocol):
    def select_workers(self, chunk_index: int, candidates: list[WorkerInfo], count: int) -> list[WorkerInfo]:
        """Pick `count` distinct workers from healthy candidates."""
        ...


class LeastLoadedPlacement:
    """Intended default: prefer workers with the lowest used_bytes, never repeat a worker."""

    def select_workers(self, chunk_index: int, candidates: list[WorkerInfo], count: int) -> list[WorkerInfo]:
        raise NotImplementedError
