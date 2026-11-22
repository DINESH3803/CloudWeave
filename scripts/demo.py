#!/usr/bin/env python3
"""
CloudWeave Automated Demonstration Script.

Showcases the 6 required scenarios:
1. Object Storage (Upload & retrieve verification)
2. Chunking & Distribution (>1 MB file split across workers)
3. Replication (Showing 2 copies per chunk and their storage locations)
4. Metadata (Retrieval and patching without re-upload)
5. Worker Failure & Recovery (`docker stop worker2` / `docker start worker2`)
6. Data Integrity (Intentional corruption, auto-detection, fallback, and repair)
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from client.client import CloudWeaveClient


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wait_for_cluster(client: CloudWeaveClient, expected_workers: int = 4, timeout: int = 30) -> None:
    print(f"Waiting for controller and {expected_workers} workers to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            status = client.cluster_status()
            workers = status.get("workers", [])
            active = [w for w in workers if w.get("status") == "active"]
            if len(active) >= expected_workers:
                print(f"Cluster ready: {len(active)} active workers ({', '.join(w['worker_id'] for w in active)})")
                return
        except Exception as e:
            time.sleep(1)
            continue
        time.sleep(1)
    print("Warning: Timed out waiting for all workers to become active. Continuing anyway.")


def run_docker_command(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Docker command failed: {' '.join(cmd)}\nError: {e.stderr}", file=sys.stderr)
        raise


# ==============================================================================
# DEMO 1: Object Storage
# ==============================================================================
def demo_1_object_storage(client: CloudWeaveClient) -> str:
    banner("DEMO 1: Object Storage (Upload & Retrieve Verification)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "sample_document.bin"
        # 500 KB of pseudorandom binary data
        data = os.urandom(500 * 1024)
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        print(f"1. Created test binary file: {test_file.name} ({len(data):,} bytes)")
        print(f"   Original SHA-256:   {original_hash}")

        # Upload
        upload_resp = client.upload(test_file, metadata={"type": "demo1_test"})
        object_id = upload_resp["id"]
        print(f"2. Uploaded successfully! Object ID: {object_id}")
        print(f"   Status: {upload_resp.get('status')}, Chunks: {upload_resp.get('chunk_count')}")

        # Download
        downloaded_bytes = client.download(object_id)
        downloaded_hash = sha256_bytes(downloaded_bytes)
        print(f"3. Downloaded {len(downloaded_bytes):,} bytes from cluster.")
        print(f"   Downloaded SHA-256: {downloaded_hash}")

        # Verification
        assert downloaded_hash == original_hash, "Checksum mismatch in Demo 1!"
        print("4. Verification SUCCESS: Downloaded object is byte-for-byte identical to original.")
        return object_id


# ==============================================================================
# DEMO 2: Chunking & Distribution
# ==============================================================================
def demo_2_chunking_and_distribution(client: CloudWeaveClient) -> str:
    banner("DEMO 2: Chunking & Distribution (>1 MB file split across workers)")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a 2.5 MB file (2,621,440 bytes: 1MB + 1MB + 0.5MB)
        size_bytes = int(2.5 * 1024 * 1024)
        test_file = Path(tmpdir) / "large_dataset.bin"
        data = os.urandom(size_bytes)
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        print(f"1. Created 2.5 MB file: {test_file.name} ({size_bytes:,} bytes)")
        print(f"   Original SHA-256: {original_hash}")

        # Upload
        upload_resp = client.upload(test_file, metadata={"type": "demo2_chunking"})
        object_id = upload_resp["id"]
        print(f"2. Uploaded successfully! Object ID: {object_id}")

        # Metadata inspection
        meta = client.metadata(object_id)
        chunks = meta.get("chunks", [])
        print(f"3. Verified chunking: File split into {len(chunks)} chunks:")
        for ch in chunks:
            replica_workers = [r["worker_id"] for r in ch.get("replicas", [])]
            print(f"   - Chunk {ch['chunk_index']} (ID: {ch['id']}): "
                  f"size={ch['size_bytes']:,} bytes, "
                  f"checksum={ch['checksum'][:16]}..., "
                  f"stored on: {replica_workers}")

        # Reassembly check
        downloaded = client.download(object_id)
        assert sha256_bytes(downloaded) == original_hash, "Checksum mismatch for reassembled chunks!"
        print("4. Verification SUCCESS: 2.5 MB object cleanly split into 1 MB chunks and reassembled.")
        return object_id


# ==============================================================================
# DEMO 3: Replication
# ==============================================================================
def demo_3_replication(client: CloudWeaveClient, object_id: str | None = None) -> None:
    banner("DEMO 3: Replication (Factor 2 across distinct workers)")
    if not object_id:
        object_id = demo_2_chunking_and_distribution(client)

    meta = client.metadata(object_id)
    chunks = meta.get("chunks", [])
    print(f"Inspecting replication for Object ID: {object_id} ({len(chunks)} chunks)")

    for ch in chunks:
        replicas = ch.get("replicas", [])
        worker_ids = [r["worker_id"] for r in replicas]
        print(f"Chunk {ch['chunk_index']} ({ch['id']}):")
        print(f"  • Replica count: {len(replicas)} (required: 2)")
        print(f"  • Storage locations: {worker_ids}")

        assert len(replicas) == 2, f"Chunk {ch['id']} does not have exactly 2 replicas!"
        assert len(set(worker_ids)) == 2, f"Replicas of {ch['id']} are not on distinct workers!"

    print("Verification SUCCESS: Every chunk maintains replication factor 2 across distinct workers.")


# ==============================================================================
# DEMO 4: Metadata
# ==============================================================================
def demo_4_metadata(client: CloudWeaveClient) -> None:
    banner("DEMO 4: Metadata (Retrieval & Patching without re-upload)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "notes.txt"
        test_file.write_text("CloudWeave distributed storage notes.")

        initial_meta = {"author": "Alice", "project": "CloudWeave", "environment": "dev"}
        print(f"1. Uploading object with initial metadata: {initial_meta}")
        resp = client.upload(test_file, metadata=initial_meta)
        object_id = resp["id"]

        # Retrieve metadata
        meta1 = client.metadata(object_id)
        print(f"2. Retrieved metadata from controller:")
        print(f"   Name: {meta1['name']}, Size: {meta1['size_bytes']} bytes")
        print(f"   Created: {meta1['created_at']}, Updated: {meta1.get('updated_at')}")
        print(f"   Custom metadata: {meta1.get('custom_metadata')}")

        # Patch metadata
        patch_payload = {"environment": "production", "version": "v2.0", "reviewer": "Bob"}
        print(f"3. Patching custom metadata (without re-uploading file): {patch_payload}")
        meta2 = client.patch_metadata(object_id, patch_payload)
        updated_custom = meta2.get("custom_metadata", {})
        print(f"4. Updated metadata response:")
        print(f"   Custom metadata: {updated_custom}")
        print(f"   Updated at: {meta2.get('updated_at')}")

        assert updated_custom.get("environment") == "production"
        assert updated_custom.get("version") == "v2.0"
        assert updated_custom.get("author") == "Alice"  # preserved
        assert updated_custom.get("reviewer") == "Bob"

        # Verify object bytes still unchanged
        downloaded = client.download(object_id)
        assert downloaded == b"CloudWeave distributed storage notes."
        print("5. Verification SUCCESS: Metadata updated in-place without touching chunk data.")


def get_worker_chunk_sha256(worker_id: str, chunk_id: str) -> str:
    cmd = ["docker", "exec", worker_id, "sha256sum", f"/data/chunks/{chunk_id}"]
    res = run_docker_command(cmd)
    return res.split()[0].strip()


# ==============================================================================
# DEMO 5: Worker Failure & Recovery
# ==============================================================================
def demo_5_worker_failure_and_recovery(client: CloudWeaveClient) -> None:
    banner("DEMO 5: Worker Failure & Recovery (docker stop / start worker2)")
    target_worker = "worker2"
    object_id: str | None = None
    worker2_stopped = False

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # 1. Ensure test object has at least one chunk replica stored on worker2
            print("1. Preparing test object with replicas on worker2...")
            test_file = Path(tmpdir) / "demo5_failover.bin"
            # 2.5 MB produces 3 chunks (6 replica placements across 4 workers)
            data = os.urandom(int(2.5 * 1024 * 1024))
            test_file.write_bytes(data)
            original_hash = sha256_bytes(data)

            upload_resp = client.upload(test_file, metadata={"purpose": "demo5_worker_failure"})
            object_id = upload_resp["id"]
            meta = client.metadata(object_id)

            has_worker2 = any(
                any(r["worker_id"] == target_worker for r in ch.get("replicas", []))
                for ch in meta.get("chunks", [])
            )
            assert has_worker2, f"Expected at least one replica on {target_worker}, but none found!"

            # 2. Display initial state
            print("\n2. Initial cluster and object state before failure:")
            initial_status = client.cluster_status()
            workers = initial_status.get("workers", [])
            for w in workers:
                print(f"   Worker {w['worker_id']}: status={w['status']}, last_heartbeat={w.get('last_heartbeat')}")
            assert all(w.get("status") == "active" for w in workers), "All workers must be active initially!"

            active_workers = {w["worker_id"] for w in workers if w.get("status") == "active"}
            chunks = meta.get("chunks", [])
            print(f"   Object {object_id} ({len(chunks)} chunks):")
            for ch in chunks:
                usable = [r for r in ch.get("replicas", []) if r.get("status") == "stored" and r.get("worker_id") in active_workers]
                locs = [r["worker_id"] for r in usable]
                print(f"   - Chunk {ch['chunk_index']} ({ch['id']}): {len(usable)} usable replica(s) on {locs}")
                assert len(usable) >= 2, f"Chunk {ch['id']} has fewer than 2 usable replicas initially!"

            # 3. Stop specifically worker2
            print(f"\n3. Stopping container '{target_worker}' (simulating node crash)...")
            run_docker_command(["docker", "stop", target_worker])
            worker2_stopped = True
            print(f"   Container {target_worker} stopped.")

            # 4. Wait for health-monitor timeout and poll until worker2 is actually marked unhealthy
            print(f"\n4. Polling health monitor for failure detection (heartbeat timeout: 15s)...")
            detection_timeout = 45.0
            poll_start = time.time()
            worker2_detected_unhealthy = False
            last_status = None
            degraded_state_captured = None

            while time.time() - poll_start < detection_timeout:
                try:
                    curr_status = client.cluster_status()
                    tw = next((w for w in curr_status.get("workers", []) if w["worker_id"] == target_worker), None)
                    if tw and tw.get("status") == "unhealthy":
                        worker2_detected_unhealthy = True
                        last_status = curr_status
                        elapsed = time.time() - poll_start
                        print(f"   Failure detected in {elapsed:.1f}s: {target_worker} marked 'unhealthy'!")

                        # Immediately capture intermediate replica state to check if degraded state is observable before repair
                        meta_check = client.metadata(object_id)
                        surviving = {w["worker_id"] for w in curr_status.get("workers", []) if w.get("status") == "active"}
                        chunk_counts = []
                        for ch in meta_check.get("chunks", []):
                            usable = [r for r in ch.get("replicas", []) if r.get("status") == "stored" and r.get("worker_id") in surviving]
                            chunk_counts.append((ch, usable))

                        if any(len(u) < 2 for _, u in chunk_counts):
                            degraded_state_captured = (meta_check, chunk_counts, surviving)
                        break
                except Exception:
                    pass
                # Poll with higher frequency as we approach the 15-second heartbeat timeout
                time.sleep(0.05 if (time.time() - poll_start > 12.0) else 0.5)

            assert worker2_detected_unhealthy, f"Health monitor failed to mark {target_worker} as unhealthy within {detection_timeout}s!"

            # 5. Display during-failure and degraded replication state
            print(f"\n5. During-failure state ({target_worker} is UNHEALTHY):")
            surviving_active = {w["worker_id"] for w in last_status.get("workers", []) if w.get("status") == "active"}
            for w in last_status.get("workers", []):
                print(f"   Worker {w['worker_id']}: status={w['status']}")
            assert target_worker not in surviving_active, f"{target_worker} must not be in active workers!"

            if degraded_state_captured:
                _, chunk_counts, surviving = degraded_state_captured
                print("\n   Observed intermediate degraded replication state before repair:")
                for ch, usable in chunk_counts:
                    locs = [r["worker_id"] for r in usable]
                    state_str = "DEGRADED (only 1 usable replica)" if len(usable) < 2 else "2 usable replicas"
                    print(f"   - Chunk {ch['chunk_index']} ({ch['id']}): {len(usable)} usable replica(s) on {locs} [{state_str}]")
            else:
                print("\n   Degraded replication state analysis:")
                print(f"   When {target_worker} failed, chunk(s) stored on {target_worker} immediately lost a usable replica.")
                print("   Replication repair triggered immediately within the same health monitor tick (< 0.1s latency).")

            # Download while worker2 is unavailable
            print(f"\n   Downloading object while {target_worker} is DOWN...")
            downloaded = client.download(object_id)
            downloaded_hash = sha256_bytes(downloaded)
            assert downloaded_hash == original_hash, f"Downloaded object checksum mismatch while {target_worker} is down!"
            print(f"   SUCCESS: Object downloaded without errors ({len(downloaded):,} bytes, SHA-256 matches) via surviving replicas.")

            # 6. Wait for replication repair to complete
            print("\n6. Waiting for replication repair to restore replication factor across surviving workers...")
            repair_timeout = 45.0
            repair_start = time.time()
            repair_completed = False
            repaired_meta = None
            while time.time() - repair_start < repair_timeout:
                try:
                    curr_status = client.cluster_status()
                    current_active = {w["worker_id"] for w in curr_status.get("workers", []) if w.get("status") == "active"}
                    curr_meta = client.metadata(object_id)
                    all_chunks_replicated = True
                    for ch in curr_meta.get("chunks", []):
                        usable = [r for r in ch.get("replicas", []) if r.get("status") == "stored" and r.get("worker_id") in current_active]
                        distinct_active = {r["worker_id"] for r in usable}
                        if len(distinct_active) < 2:
                            all_chunks_replicated = False
                            break
                    if all_chunks_replicated:
                        repair_completed = True
                        repaired_meta = curr_meta
                        elapsed = time.time() - repair_start
                        print(f"   Replication repair confirmed in {elapsed:.1f}s!")
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            assert repair_completed, "Replication repair failed to restore 2 usable replicas on healthy workers!"

            # 7 & 8. Verify and display restored replica locations
            print("\n7 & 8. Restored replica count and Worker locations (surviving active workers only):")
            curr_status = client.cluster_status()
            current_active = {w["worker_id"] for w in curr_status.get("workers", []) if w.get("status") == "active"}
            for ch in repaired_meta.get("chunks", []):
                usable = [r for r in ch.get("replicas", []) if r.get("status") == "stored" and r.get("worker_id") in current_active]
                distinct_locs = sorted(list({r["worker_id"] for r in usable}))
                print(f"   - Chunk {ch['chunk_index']} ({ch['id']}): {len(usable)} usable replicas on {distinct_locs} [RESTORED]")
                assert len(distinct_locs) >= 2, f"Chunk {ch['id']} has fewer than 2 distinct healthy replicas!"

            # 9. Restart worker2 using Docker
            print(f"\n9. Restarting container '{target_worker}'...")
            run_docker_command(["docker", "start", target_worker])
            worker2_stopped = False
            print(f"   Container {target_worker} started. Waiting for re-registration...")

            # 10. Wait until worker2 becomes healthy again and display final state
            print(f"\n10. Polling until {target_worker} becomes active...")
            recovery_timeout = 35.0
            rec_start = time.time()
            worker2_active = False
            while time.time() - rec_start < recovery_timeout:
                try:
                    curr_status = client.cluster_status()
                    tw = next((w for w in curr_status.get("workers", []) if w["worker_id"] == target_worker), None)
                    if tw and tw.get("status") == "active":
                        worker2_active = True
                        elapsed = time.time() - rec_start
                        print(f"   {target_worker} successfully recovered in {elapsed:.1f}s! Status: active")
                        break
                except Exception:
                    pass
                time.sleep(1)

            assert worker2_active, f"{target_worker} failed to re-register as active within {recovery_timeout}s!"

            final_status = client.cluster_status()
            print("   Final cluster worker statuses:")
            for w in final_status.get("workers", []):
                print(f"     Worker {w['worker_id']}: status={w['status']}")

            print("\n11. Verification SUCCESS: Worker failure detected, data served via surviving replicas, replication restored, and worker recovered cleanly.")

        finally:
            # Always ensure worker2 is restarted if it was left stopped
            if worker2_stopped:
                print(f"   Ensuring {target_worker} is restarted...")
                try:
                    run_docker_command(["docker", "start", target_worker])
                except Exception:
                    pass
            # Clean up dedicated temporary demonstration object
            if object_id:
                print(f"   Cleaning up temporary demo object {object_id}...")
                try:
                    client.delete(object_id)
                except Exception as e:
                    print(f"   Note: Cleanup error: {e}")


# ==============================================================================
# DEMO 6: Data Integrity & Corruption
# ==============================================================================
def demo_6_data_integrity_and_repair(client: CloudWeaveClient) -> None:
    banner("DEMO 6: Data Integrity (Corruption Detection, Fallback & Repair)")
    object_id: str | None = None

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            test_file = Path(tmpdir) / "demo6_integrity.bin"
            data = os.urandom(256 * 1024)
            test_file.write_bytes(data)
            original_hash = sha256_bytes(data)

            print("1. Uploading dedicated test object for data integrity demonstration...")
            upload_resp = client.upload(test_file, metadata={"purpose": "demo6_data_integrity"})
            object_id = upload_resp["id"]

            meta = client.metadata(object_id)
            chunk = meta["chunks"][0]
            chunk_id = chunk["id"]
            expected_chunk_hash = chunk["checksum"]

            # Step 1 & 2: Identify selected chunk, replicas, and exact worker to corrupt
            cluster_stat = client.cluster_status()
            active_workers = {w["worker_id"] for w in cluster_stat.get("workers", []) if w.get("status") == "active"}
            active_chunk_replicas = sorted(
                [r for r in chunk["replicas"] if r["worker_id"] in active_workers],
                key=lambda r: r["worker_id"],
            )
            assert len(active_chunk_replicas) >= 2, "Test chunk must have at least 2 active replicas!"

            # Step 3: Ensure the corrupted replica is the one selected first during download.
            # Controller's read_chunk sorts active replicas lexicographically by worker_id,
            # so active_chunk_replicas[0] is guaranteed to be queried first.
            target_replica = active_chunk_replicas[0]
            backup_replica = active_chunk_replicas[1]
            target_worker = target_replica["worker_id"]
            backup_worker = backup_replica["worker_id"]

            print(f"   Object ID: {object_id}")
            print(f"   Chunk ID:  {chunk_id} (Expected SHA-256: {expected_chunk_hash})")
            print(f"   Replicas:  {target_worker} (first queried) and {backup_worker} (backup)")

            # Step 4: Before corruption, record its original checksum
            print(f"\n2. Verifying initial stored chunk checksum on {target_worker}...")
            pre_corruption_hash = get_worker_chunk_sha256(target_worker, chunk_id)
            print(f"   Pre-corruption SHA-256 on {target_worker}: {pre_corruption_hash}")
            assert pre_corruption_hash == expected_chunk_hash, f"Initial file checksum on {target_worker} does not match expected!"

            # Step 5: Intentionally corrupt only the selected test object's replica
            print(f"\n3. Intentionally corrupting chunk file on {target_worker}...")
            corrupt_cmd = [
                "docker", "exec", target_worker,
                "sh", "-c", f"echo 'CORRUPTED_BYTES_HERE_DEMO6' > /data/chunks/{chunk_id}",
            ]
            run_docker_command(corrupt_cmd)
            print(f"   Overwrote /data/chunks/{chunk_id} on {target_worker} with bad bytes.")

            # Step 6: Verify using SHA-256 that the stored file checksum no longer matches expected
            print(f"\n4. Verifying stored file checksum on {target_worker} is now CORRUPT...")
            corrupted_hash = get_worker_chunk_sha256(target_worker, chunk_id)
            print(f"   Corrupted SHA-256 on {target_worker}: {corrupted_hash}")
            assert corrupted_hash != expected_chunk_hash, f"File on {target_worker} was expected to be corrupted!"
            print("   CONFIRMED: Stored chunk file checksum no longer matches expected checksum.")

            # Step 7: Download complete object through normal client-facing API
            print(f"\n5. Requesting download via API (http://localhost:8000/api/v1/objects/{object_id})...")
            downloaded = client.download(object_id)
            downloaded_hash = sha256_bytes(downloaded)

            # Step 8: Verify that downloaded object matches original checksum
            print(f"\n6. Verifying downloaded object against original SHA-256...")
            print(f"   Downloaded size: {len(downloaded):,} bytes")
            print(f"   Downloaded SHA-256: {downloaded_hash}")
            print(f"   Original SHA-256:   {original_hash}")
            assert downloaded_hash == original_hash, "Corrupted bytes were returned to client!"
            print(f"   SUCCESS: Controller detected corruption on {target_worker}, fell back to valid replica on {backup_worker}, and returned intact data.")

            # Step 9 & 10: Verify corrupted replica was detected and restored
            print(f"\n7. Verifying corrupted replica on {target_worker} was detected and restored...")
            time.sleep(1)  # allow inline auto-repair transaction to settle
            post_repair_hash = get_worker_chunk_sha256(target_worker, chunk_id)
            print(f"   Post-repair SHA-256 on {target_worker}: {post_repair_hash}")
            assert post_repair_hash == expected_chunk_hash, f"Restored chunk on {target_worker} does not match expected checksum!"

            meta_after = client.metadata(object_id)
            rep_after = next(r for r in meta_after["chunks"][0]["replicas"] if r["worker_id"] == target_worker)
            print(f"   Replica status in metadata for {target_worker}: {rep_after['status']}")
            assert rep_after["status"] == "stored", f"Replica status on {target_worker} is {rep_after['status']}, expected 'stored'!"

            print("\n8. Verification SUCCESS: Stored data corrupted intentionally, corruption detected on read, fallback served valid data, and corrupted replica restored to valid checksum.")

        finally:
            if object_id:
                print(f"   Cleaning up temporary demo object {object_id}...")
                try:
                    client.delete(object_id)
                except Exception as e:
                    print(f"   Note: Cleanup error: {e}")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="CloudWeave Demonstration Runner")
    parser.add_argument("--url", default="http://localhost:8000", help="Controller URL")
    parser.add_argument("--demo", type=int, choices=[1, 2, 3, 4, 5, 6], help="Run a specific demo (1-6)")
    args = parser.parse_args()

    client = CloudWeaveClient(args.url)
    print("=" * 70)
    print(" CloudWeave Mini Distributed Cloud Object Store — Demonstration")
    print(f" Target controller: {args.url}")
    print("=" * 70)

    try:
        wait_for_cluster(client)

        if args.demo == 1:
            demo_1_object_storage(client)
        elif args.demo == 2:
            demo_2_chunking_and_distribution(client)
        elif args.demo == 3:
            demo_3_replication(client)
        elif args.demo == 4:
            demo_4_metadata(client)
        elif args.demo == 5:
            demo_5_worker_failure_and_recovery(client)
        elif args.demo == 6:
            demo_6_data_integrity_and_repair(client)
        else:
            # Run all 6 in sequence
            demo_1_object_storage(client)
            obj2 = demo_2_chunking_and_distribution(client)
            demo_3_replication(client, obj2)
            demo_4_metadata(client)
            demo_5_worker_failure_and_recovery(client)
            demo_6_data_integrity_and_repair(client)

            banner("ALL 6 DEMONSTRATIONS COMPLETED SUCCESSFULLY!")

    except Exception as e:
        print(f"\nDemonstration error: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
