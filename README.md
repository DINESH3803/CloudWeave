# CloudWeave — Mini Distributed Cloud Object Store

CloudWeave is a fault-tolerant distributed cloud object store built with Python 3.12, FastAPI, PostgreSQL, and Docker Compose. It stores arbitrary binary files (documents, images, videos, audio, compressed archives) by splitting them into **1 MB chunks** and replicating each chunk across 4 persistent worker nodes with a strict **replication factor of 2**.

---

## 1. System Architecture

```text
            ┌─────────┐   REST API (/api/v1)   ┌──────────────────────┐    SQL     ┌────────────┐
  client ──▶│  CLI /  │───────────────────────▶│      controller      │───────────▶│ PostgreSQL │
            │ scripts │                        │ (FastAPI, metadata,  │ (port 5432)└────────────┘
            └─────────┘                        │  placement, repair)  │
                                               └──────────┬───────────┘
                                         internal HTTP    │  ▲ register / heartbeat (5s)
                                    ┌───────────┬─────────┼──┴────┬───────────┐
                                    ▼           ▼         ▼       ▼
                                 worker1     worker2   worker3  worker4   (persistent /data/chunks)
```

- **Controller (`controller`, port 8000)**: Coordinates upload chunking, download reassembly, least-loaded placement, worker registry, background health monitoring, under-replication healing, and metadata persistence.
- **Workers (`worker1` to `worker4`, port 8001 internal)**: 4 autonomous storage nodes that persist chunk files on independent volumes (`/data/chunks`), send periodic heartbeats (every 5s), and serve internal chunk transfer requests.
- **PostgreSQL (`postgres`, port 5432)**: Relational metadata database storing object records, chunk hashes, replica locations, and worker nodes.

---

## 2. Prerequisites (Windows / PowerShell)

Before setting up CloudWeave, make sure you have:
1. **Docker Desktop for Windows** (with WSL2 backend enabled and running).
2. **Python 3.10+** installed on Windows and added to your `PATH`.
3. A terminal: **PowerShell** (recommended) or **Command Prompt (cmd)**.

---

## 3. Quick Setup from Scratch (Step-by-Step)

### Step 1: Clone and Navigate to Project Directory

Open PowerShell and navigate to the project root:
```powershell
cd C:\Users\<YourUser>\...\CloudWeave
```

### Step 2: Set Up Python Virtual Environment (Local Host)

Create and activate a virtual environment for the client CLI and test tools:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment in PowerShell
.\venv\Scripts\Activate.ps1

# Install requirements (includes httpx, pytest, pydantic, etc.)
pip install -r requirements.txt
```

*(If PowerShell blocks script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in your session).*

### Step 3: Configure Environment File

Ensure `.env` exists in the repository root:
```powershell
Copy-Item .env.example .env -Force
```
*(The default settings in `.env` are pre-configured to work out of the box).*

### Step 4: Build and Start the Cluster with Docker Compose

Build the container images and start all 6 containers (`postgres`, `controller`, and `worker1` through `worker4`):

```powershell
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

### Step 5: Verify Cluster Health

Check that all 6 containers are running and healthy:
```powershell
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

You can also check the cluster status directly via the client CLI:
```powershell
python -m client.cli cluster
```

The controller web endpoints are available at:
- **Interactive OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Controller Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 4. Running the 6 Required Demonstrations

An automated runner script is provided under `scripts/demo.py` to demonstrate and verify all 6 required project specifications:

```powershell
python scripts/demo.py
```

### Demonstration Scenarios Covered:

1. **Object Storage (`demo 1`)**: Uploads an arbitrary binary file and downloads it back, verifying byte-for-byte SHA-256 match.
2. **Chunking & Distribution (`demo 2`)**: Uploads a > 1 MB file (2.5 MB), verifies splitting into 1 MB chunks and fair distribution across workers.
3. **Replication (`demo 3`)**: Inspects chunk metadata to prove each chunk has exactly 2 copies residing on distinct worker nodes.
4. **Metadata Management (`demo 4`)**: Uploads custom metadata, retrieves it, and updates/patches metadata in-place via `PATCH` without re-uploading file bytes.
5. **Worker Failure & Recovery (`demo 5`)**: Uploads a dedicated test object with replicas on `worker2`, displays initial worker health and replica locations, stops `worker2` via `docker stop worker2`, polls health monitor until failure is detected (`worker2` marked unhealthy), displays during-failure state and successfully downloads/verifies the object via surviving replicas, waits for replication reconciliation to restore 2 usable copies per chunk on surviving healthy workers, restarts `worker2` via `docker start worker2`, polls until `worker2` re-registers as active, and cleans up the temporary demonstration object.
6. **Data Integrity & Corruption Repair (`demo 6`)**: Uploads a dedicated test object, identifies the first-queried replica deterministically, records initial on-disk SHA-256 checksum, intentionally corrupts the chunk file on the target worker's disk and verifies checksum mismatch, downloads the object via the client API to demonstrate corruption detection and seamless fallback to a valid replica, verifies that read-repair restores the corrupted worker replica to its valid on-disk SHA-256 and `stored` status, and cleans up the temporary demonstration object.

You can also run any specific scenario individually:
```powershell
python scripts/demo.py --demo 1
python scripts/demo.py --demo 5
```

---

## 5. Client CLI Usage (Interactive)

The command-line interface is available via `python -m client.cli`:

```powershell
# Upload an object with custom JSON metadata
python -m client.cli upload .\README.md --metadata '{"author":"Pardhiv","project":"CloudWeave"}'

# List all stored objects
python -m client.cli list

# View complete metadata and chunk locations for an object
python -m client.cli metadata <OBJECT_ID>

# Modify metadata in-place without re-uploading file chunks
python -m client.cli patch-metadata <OBJECT_ID> '{"status":"approved","reviewer":"Dinesh"}'

# Download and reassemble an object
python -m client.cli download <OBJECT_ID> .\downloaded_file.bin

# Delete an object and purge its chunks across all workers
python -m client.cli delete <OBJECT_ID>

# Query cluster health and active workers
python -m client.cli cluster
```

---

## 6. Running the Automated Test Suite

Run unit and integration tests using pytest:

```powershell
python -m pytest tests/
```

---

## 7. Cluster Shutdown

```powershell
# Stop cluster containers (preserves worker and database volumes)
docker compose --env-file .env -f deploy/docker-compose.yml down

# Stop cluster and wipe all persistent storage volumes
docker compose --env-file .env -f deploy/docker-compose.yml down -v
```

---

## 8. Documentation & Project Report

The complete academic project report is located at:
- **[docs/CloudWeave.md](file:///c:/Users/Pardh/.antigravity-ide/CloudWeave/docs/CloudWeave.md)**
