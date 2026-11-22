"""
Chunk Placement Strategy.

Decides which worker nodes receive replicas of each chunk to ensure:
- Balanced load distribution across worker nodes.
- Distinct placement (replicas of a chunk are never placed on the same worker).
"""
from typing import Protocol

from shared.exceptions import NoHealthyWorkersError
from shared.models import WorkerInfo


class PlacementStrategy(Protocol):
    """Interface for replica placement algorithms."""

    def select_workers(self, chunk_index: int, candidates: list[WorkerInfo], count: int) -> list[WorkerInfo]:
        """Pick `count` distinct workers from healthy candidate workers."""
        ...


class LeastLoadedPlacement:
    """
    Least-Loaded Placement Strategy.
    
    Prefers workers with the lowest current disk load (used_bytes).
    Applies a round-robin rotation based on chunk_index to interleave placement
    among workers that have equal storage load.
    """

    def select_workers(
        self, chunk_index: int, candidates: list[WorkerInfo], count: int
    ) -> list[WorkerInfo]:
        """Select `count` distinct workers from healthy candidates with least load."""
        # Ensure we have at least 'count' distinct candidate workers available
        if len(candidates) < count:
            raise NoHealthyWorkersError(
                f"Requested {count} workers for replica placement, but only {len(candidates)} healthy workers available"
            )

        # Shift candidate order by chunk_index to interleave placement across workers with equal load
        n = len(candidates)
        shifted = [candidates[(i + chunk_index) % n] for i in range(n)]
        
        # Sort candidates ascending by used_bytes (least loaded first)
        sorted_candidates = sorted(shifted, key=lambda w: w.used_bytes)

        # Collect 'count' distinct workers
        selected: list[WorkerInfo] = []
        for worker in sorted_candidates:
            if worker not in selected:
                selected.append(worker)
            if len(selected) == count:
                break

        return selected
