"""
Failure Recovery and Scheduler Placement Tests.
Tests least-loaded candidate selection, distinct worker assignment,
and error handling when insufficient healthy workers are online.
"""
import unittest

from controller.app.scheduler.placement import LeastLoadedPlacement
from shared.exceptions import NoHealthyWorkersError
from shared.models import WorkerInfo


class TestFailureRecovery(unittest.TestCase):
    """Verifies worker selection algorithms and replica placement constraints."""

    def test_least_loaded_placement(self):
        """Test that scheduler chooses candidate workers with lowest disk usage."""
        placement = LeastLoadedPlacement()
        candidates = [
            WorkerInfo(worker_id="w1", base_url="http://w1:8001", used_bytes=100),
            WorkerInfo(worker_id="w2", base_url="http://w2:8001", used_bytes=300),
            WorkerInfo(worker_id="w3", base_url="http://w3:8001", used_bytes=200),
            WorkerInfo(worker_id="w4", base_url="http://w4:8001", used_bytes=50),
        ]

        # Select 2 workers: w4 (50 bytes) and w1 (100 bytes) should be selected
        chosen = placement.select_workers(chunk_index=0, candidates=candidates, count=2)
        chosen_ids = {w.worker_id for w in chosen}
        self.assertEqual(len(chosen), 2)
        self.assertIn("w4", chosen_ids)
        self.assertIn("w1", chosen_ids)

    def test_insufficient_workers_raises(self):
        """Test that requesting more replicas than available workers raises NoHealthyWorkersError."""
        placement = LeastLoadedPlacement()
        candidates = [
            WorkerInfo(worker_id="w1", base_url="http://w1:8001", used_bytes=100),
        ]

        # Expect NoHealthyWorkersError when requesting 2 replicas from only 1 worker
        with self.assertRaises(NoHealthyWorkersError):
            placement.select_workers(chunk_index=0, candidates=candidates, count=2)


if __name__ == "__main__":
    unittest.main()
