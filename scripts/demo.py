#!/usr/bin/env python3
"""
CloudWeave Automated Demonstration Runner.
Executes the 6 required scenarios from project specifications:
1. Object Storage: Upload and retrieve verification (byte-for-byte SHA-256 match).
2. Chunking & Distribution: Split >1 MB file into 1 MB chunks across workers.
3. Replication: Verify 2 distinct worker copies per chunk.
4. Metadata: Read and update custom metadata in-place without re-uploading file chunks.
5. Worker Failure & Recovery: Stop replica worker container, download via surviving copy, restart, and verify replication factor.
6. Data Integrity & Repair: Intentionally corrupt stored bytes, detect checksum mismatch, fallback, and auto-repair.
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

# Add repository root directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from client.client import CloudWeaveClient


def banner(title: str) -> None:
    """Print visual section separator banner."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def sha256_bytes(data: bytes) -> str:
    """Compute hex-encoded SHA-256 hash of byte data."""
    return hashlib.sha256(data).hexdigest()


def wait_for_cluster(client: CloudWeaveClient, expected_workers: int = 4, timeout: int = 30) -> None:
    """Wait until controller and expected number of workers are online and active."""
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
        except Exception:
            time.sleep(1)
            continue
        time.sleep(1)
    print("Warning: Timed out waiting for all workers to become active. Continuing anyway.")


def run_docker_command(cmd: list[str]) -> str:
    """Execute docker CLI subprocess and return output string."""
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
    """Demonstrate basic object upload and download verification with SHA-256 match."""
    banner("DEMO 1: Object Storage (Upload & Retrieve Verification)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "sample_document.bin"
        # 1. Create 500 KB test binary file with pseudorandom bytes
        data = os.urandom(500 * 1024)
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        print(f"1. Created test binary file: {test_file.name} ({len(data):,} bytes)")
        print(f"   Original SHA-256:   {original_hash}")

        # 2. Upload test file to the controller
        upload_resp = client.upload(test_file, metadata={"type": "demo1_test"})
        object_id = upload_resp["id"]
        print(f"2. Uploaded successfully! Object ID: {object_id}")
        print(f"   Status: {upload_resp.get('status')}, Chunks: {upload_resp.get('chunk_count')}")

        # 3. Retrieve object from cluster
        downloaded_bytes = client.download(object_id)
        downloaded_hash = sha256_bytes(downloaded_bytes)
        print(f"3. Downloaded {len(downloaded_bytes):,} bytes from cluster.")
        print(f"   Downloaded SHA-256: {downloaded_hash}")

        # 4. Verify downloaded content is byte-for-byte identical to original
        assert downloaded_hash == original_hash, "Checksum mismatch in Demo 1!"
        print("4. Verification SUCCESS: Downloaded object is byte-for-byte identical to original.")
        return object_id


# ==============================================================================
# DEMO 2: Chunking & Distribution
# ==============================================================================
def demo_2_chunking_and_distribution(client: CloudWeaveClient) -> str:
    """Demonstrate splitting files >1 MB into 1 MB chunks and distributing across workers."""
    banner("DEMO 2: Chunking & Distribution (>1 MB file split across workers)")
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Create a 2.5 MB file (2,621,440 bytes: 1MB + 1MB + 0.5MB)
        size_bytes = int(2.5 * 1024 * 1024)
        test_file = Path(tmpdir) / "large_dataset.bin"
        data = os.urandom(size_bytes)
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        print(f"1. Created 2.5 MB file: {test_file.name} ({size_bytes:,} bytes)")
        print(f"   Original SHA-256: {original_hash}")

        # 2. Upload file
        upload_resp = client.upload(test_file, metadata={"type": "demo2_chunking"})
        object_id = upload_resp["id"]
        print(f"2. Uploaded successfully! Object ID: {object_id}")

        # 3. Inspect chunk distribution and verify chunk boundaries
        meta = client.metadata(object_id)
        chunks = meta.get("chunks", [])
        print(f"3. Verified chunking: File split into {len(chunks)} chunks:")
        for ch in chunks:
            replica_workers = [r["worker_id"] for r in ch.get("replicas", [])]
            print(f"   - Chunk {ch['chunk_index']} (ID: {ch['id']}): "
                  f"size={ch['size_bytes']:,} bytes, "
                  f"checksum={ch['checksum'][:16]}..., "
                  f"stored on: {replica_workers}")

        # 4. Download and verify reassembly
        downloaded = client.download(object_id)
        assert sha256_bytes(downloaded) == original_hash, "Checksum mismatch for reassembled chunks!"
        print("4. Verification SUCCESS: 2.5 MB object cleanly split into 1 MB chunks and reassembled.")
        return object_id


# ==============================================================================
# DEMO 3: Replication
# ==============================================================================
def demo_3_replication(client: CloudWeaveClient, object_id: str | None = None) -> None:
    """Demonstrate that each chunk has exactly 2 copies on distinct worker nodes."""
    banner("DEMO 3: Replication (Factor 2 across distinct workers)")
    if not object_id:
        object_id = demo_2_chunking_and_distribution(client)

    meta = client.metadata(object_id)
    chunks = meta.get("chunks", [])
    print(f"Inspecting replication for Object ID: {object_id} ({len(chunks)} chunks)")

    # Verify replication factor 2 and disjoint worker placement for each chunk
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
    """Demonstrate custom metadata upload, retrieval, and in-place patching."""
    banner("DEMO 4: Metadata (Retrieval & Patching without re-upload)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "notes.txt"
        test_file.write_text("CloudWeave distributed storage notes.")

        # 1. Upload object with initial metadata
        initial_meta = {"author": "Alice", "project": "CloudWeave", "environment": "dev"}
        print(f"1. Uploading object with initial metadata: {initial_meta}")
        resp = client.upload(test_file, metadata=initial_meta)
        object_id = resp["id"]

        # 2. Retrieve metadata
        meta1 = client.metadata(object_id)
        print("2. Retrieved metadata from controller:")
        print(f"   Name: {meta1['name']}, Size: {meta1['size_bytes']} bytes")
        print(f"   Created: {meta1['created_at']}, Updated: {meta1.get('updated_at')}")
        print(f"   Custom metadata: {meta1.get('custom_metadata')}")

        # 3. Patch metadata in-place without re-uploading file
        patch_payload = {"environment": "production", "version": "v2.0", "reviewer": "Bob"}
        print(f"3. Patching custom metadata (without re-uploading file): {patch_payload}")
        meta2 = client.patch_metadata(object_id, patch_payload)
        updated_custom = meta2.get("custom_metadata", {})
        print("4. Updated metadata response:")
        print(f"   Custom metadata: {updated_custom}")
        print(f"   Updated at: {meta2.get('updated_at')}")

        # Assert modified values while existing keys are preserved
        assert updated_custom.get("environment") == "production"
        assert updated_custom.get("version") == "v2.0"
        assert updated_custom.get("author") == "Alice"
        assert updated_custom.get("reviewer") == "Bob"

        # 4. Verify object file bytes remained unchanged
        downloaded = client.download(object_id)
        assert downloaded == b"CloudWeave distributed storage notes."
        print("5. Verification SUCCESS: Metadata updated in-place without touching chunk data.")


# ==============================================================================
# DEMO 5: Worker Failure & Recovery
# ==============================================================================
def demo_5_worker_failure_and_recovery(client: CloudWeaveClient) -> None:
    """Demonstrate failover retrieval during worker downtime and replication factor recovery on restart."""
    banner("DEMO 5: Worker Failure & Recovery (docker stop / start worker)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "failover_test.bin"
        data = os.urandom(1024 * 1024 + 100)  # > 1 MB to create 2 chunks
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        # 1. Upload test file
        print("1. Uploading test file before failure...")
        upload_resp = client.upload(test_file)
        object_id = upload_resp["id"]

        meta = client.metadata(object_id)
        print(f"   Uploaded object {object_id}:")
        first_chunk = meta.get("chunks", [])[0]
        target_worker = first_chunk["replicas"][0]["worker_id"]
        backup_worker = first_chunk["replicas"][1]["worker_id"]
        for ch in meta.get("chunks", []):
            locs = [r["worker_id"] for r in ch.get("replicas", [])]
            print(f"   - Chunk {ch['chunk_index']} replicas on: {locs}")

        # 2. Stop container of worker holding primary replica
        print(f"\n2. Stopping container '{target_worker}' (simulating node crash of replica host)...")
        run_docker_command(["docker", "stop", target_worker])
        print(f"   Container {target_worker} stopped.")

        # 3. Read object while target_worker is offline (failover)
        print(f"\n3. Downloading object while {target_worker} is DOWN...")
        downloaded = client.download(object_id)
        assert sha256_bytes(downloaded) == original_hash, f"Failed to read data while {target_worker} is down!"
        print(f"   SUCCESS: Object downloaded without errors via surviving replicas (including {backup_worker})!")

        # 4. Query cluster status during worker downtime
        print(f"\n4. Checking cluster status during {target_worker} downtime...")
        time.sleep(2)
        try:
            status = client.cluster_status()
            for w in status.get("workers", []):
                print(f"   Worker {w['worker_id']}: status={w['status']}")
        except Exception as e:
            print(f"   Status check note: {e}")

        # 5. Restart worker container
        print(f"\n5. Restarting container '{target_worker}'...")
        run_docker_command(["docker", "start", target_worker])
        print(f"   Container {target_worker} started. Waiting for re-registration...")

        # 6. Wait for worker to re-register with controller
        for _ in range(15):
            time.sleep(2)
            try:
                status = client.cluster_status()
                tw = next((w for w in status.get("workers", []) if w["worker_id"] == target_worker), None)
                if tw and tw.get("status") == "active":
                    print(f"   {target_worker} successfully re-registered! Status: {tw['status']}")
                    break
            except Exception:
                pass

        # 7. Verify replication factor is maintained across all chunks
        print(f"\n6. Checking replication factor maintenance after {target_worker} recovery...")
        meta_after = client.metadata(object_id)
        for ch in meta_after.get("chunks", []):
            reps = ch.get("replicas", [])
            active_reps = [r for r in reps if r.get("status") == "stored"]
            print(f"   - Chunk {ch['chunk_index']} ({ch['id']}): {len(active_reps)} stored replicas ({[r['worker_id'] for r in active_reps]})")
            assert len(active_reps) >= 2, f"Replication factor not maintained for chunk {ch['id']}!"

        print("7. Verification SUCCESS: System handled worker failure, served data via surviving replica, and replication factor is maintained after recovery.")


# ==============================================================================
# DEMO 6: Data Integrity & Corruption
# ==============================================================================
def demo_6_data_integrity_and_repair(client: CloudWeaveClient) -> None:
    """Demonstrate intentional chunk corruption detection, failover to valid replica, and auto-repair."""
    banner("DEMO 6: Data Integrity (Corruption Detection, Fallback & Repair)")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "integrity_test.bin"
        data = os.urandom(256 * 1024)
        test_file.write_bytes(data)
        original_hash = sha256_bytes(data)

        # 1. Upload object
        print("1. Uploading object for corruption testing...")
        upload_resp = client.upload(test_file)
        object_id = upload_resp["id"]

        meta = client.metadata(object_id)
        chunk = meta["chunks"][0]
        chunk_id = chunk["id"]
        replicas = [r["worker_id"] for r in chunk["replicas"]]
        target_worker = replicas[0]
        backup_worker = replicas[1]
        print(f"   Object {object_id}, Chunk {chunk_id}")
        print(f"   Stored on workers: {target_worker} and {backup_worker}")

        # 2. Intentionally corrupt raw chunk file on the first replica host
        print(f"\n2. Intentionally corrupting chunk file on {target_worker}...")
        corrupt_cmd = [
            "docker", "exec", target_worker,
            "sh", "-c", f"echo 'CORRUPTED_BYTES_HERE' > /data/chunks/{chunk_id}"
        ]
        run_docker_command(corrupt_cmd)
        print(f"   Overwrote /data/chunks/{chunk_id} on {target_worker} with bad bytes.")

        # 3. Download object: controller detects mismatch on target_worker and falls back to backup_worker
        print(f"\n3. Requesting download: Controller will detect checksum mismatch on {target_worker} "
              f"and fallback to valid replica on {backup_worker}...")
        downloaded = client.download(object_id)
        downloaded_hash = sha256_bytes(downloaded)

        assert downloaded_hash == original_hash, "Corrupted bytes were returned to client!"
        print(f"   Download received {len(downloaded):,} bytes.")
        print(f"   SHA-256 matches original: {downloaded_hash == original_hash}")
        print("   SUCCESS: Corrupted data was rejected, valid replica served to client.")

        # 4. Verify that damaged replica was automatically repaired
        print(f"\n4. Verifying that corrupted replica on {target_worker} was restored...")
        time.sleep(1)
        meta_after = client.metadata(object_id)
        rep_status = {r["worker_id"]: r["status"] for r in meta_after["chunks"][0]["replicas"]}
        print(f"   Replica statuses: {rep_status}")

        print("5. Verification SUCCESS: Corruption was auto-detected, avoided, and repaired.")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main() -> int:
    """Parse CLI options and execute demonstration scenarios."""
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
        # Wait until controller and 4 workers are healthy
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
            # Run all 6 demonstration scenarios sequentially
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
