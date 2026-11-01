"""Chunk placement: decide which workers receive each chunk's replicas."""
from typing import Protocol

from shared.exceptions import NoHealthyWorkersError
from shared.models import WorkerInfo


class PlacementStrategy(Protocol):
    def select_workers(self, chunk_index: int, candidates: list[WorkerInfo], count: int) -> list[WorkerInfo]:
        """Pick `count` distinct workers from healthy candidates."""
        ...


class LeastLoadedPlacement:
    """Prefer workers with the lowest used_bytes, never repeat a worker."""

    def select_workers(
        self, chunk_index: int, candidates: list[WorkerInfo], count: int
    ) -> list[WorkerInfo]:
        if len(candidates) < count:
            raise NoHealthyWorkersError(
                f"Requested {count} workers for replica placement, but only {len(candidates)} healthy workers available"
            )

        # Stable sort with round-robin offset to balance across workers with equal load
        n = len(candidates)
        # Shift the candidate order by chunk_index to interleave placement
        shifted = [candidates[(i + chunk_index) % n] for i in range(n)]
        sorted_candidates = sorted(shifted, key=lambda w: w.used_bytes)

        selected: list[WorkerInfo] = []
        for worker in sorted_candidates:
            if worker not in selected:
                selected.append(worker)
            if len(selected) == count:
                break

        return selected
