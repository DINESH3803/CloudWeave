"""Tests for placement algorithm and replica guarantees."""
import unittest

from controller.app.scheduler.placement import LeastLoadedPlacement
from shared.exceptions import NoHealthyWorkersError
from shared.models import WorkerInfo


class TestFailureRecovery(unittest.TestCase):
    def test_least_loaded_placement(self):
        placement = LeastLoadedPlacement()

        candidates = [
            WorkerInfo(worker_id="w1", base_url="http://w1:8001", used_bytes=100),
            WorkerInfo(worker_id="w2", base_url="http://w2:8001", used_bytes=300),
            WorkerInfo(worker_id="w3", base_url="http://w3:8001", used_bytes=200),
            WorkerInfo(worker_id="w4", base_url="http://w4:8001", used_bytes=50),
        ]

        # Should pick w4 (50) and w1 (100) because they have the lowest load
        chosen = placement.select_workers(chunk_index=0, candidates=candidates, count=2)
        chosen_ids = {w.worker_id for w in chosen}
        self.assertEqual(len(chosen), 2)
        self.assertIn("w4", chosen_ids)
        self.assertIn("w1", chosen_ids)

    def test_insufficient_workers_raises(self):
        placement = LeastLoadedPlacement()
        candidates = [
            WorkerInfo(worker_id="w1", base_url="http://w1:8001", used_bytes=100),
        ]

        with self.assertRaises(NoHealthyWorkersError):
            placement.select_workers(chunk_index=0, candidates=candidates, count=2)


if __name__ == "__main__":
    unittest.main()
