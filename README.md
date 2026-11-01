# CloudWeave — Mini Distributed Cloud Object Store

CloudWeave is a distributed cloud object storage system built with Python 3.12, FastAPI, PostgreSQL, and Docker Compose. It stores arbitrary binary objects (documents, images, videos, audio, compressed files) by dividing them into 1 MB chunks and replicating each chunk across 4 persistent worker nodes with a replication factor of 2.

---

## 1. System Architecture

```
            ┌─────────┐   REST API    ┌──────────────────────┐    SQL     ┌────────────┐
  client ──▶│  CLI /  │──────────────▶│      controller      │───────────▶│ PostgreSQL │
            │ scripts │               │ (FastAPI, metadata,  │            └────────────┘
            └─────────┘               │  placement, repair)  │
                                      └──────────┬───────────┘
                                internal HTTP    │  ▲ register / heartbeat
                           ┌───────────┬─────────┼──┴────┬───────────┐
                           ▼           ▼         ▼       ▼
                        worker1     worker2   worker3  worker4   (each with persistent storage)
```

- **Controller (`controller`)**: Single coordination node managing the client REST API, chunking/reassembly, object metadata, chunk placement, worker registry, heartbeat health monitoring, replication restoration, and integrity repair.
- **Workers (`worker1` - `worker4`)**: 4 autonomous storage nodes that store chunks on persistent disk volumes (`/data/chunks`), register with the controller, emit periodic heartbeats, and serve internal chunk storage/retrieval/verification requests.
- **PostgreSQL (`postgres`)**: Relational database storing metadata for objects, chunks, chunk replica mappings, and worker statuses.

---

## 2. Prerequisites

- **Docker** (v20+ or Docker Desktop)
- **Docker Compose** (v2+)
- **Python 3.10+** (with `httpx` installed for running client CLI / demo scripts locally)

---

## 3. Quick Start

### Step 1: Configure Environment

```bash
cp .env.example .env
```
*(Default settings in `.env` are pre-configured to run out of the box).*

### Step 2: Build and Start the Cluster

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

Verify that all 6 containers (`postgres`, `controller`, `worker1`, `worker2`, `worker3`, `worker4`) are up and healthy:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

The controller REST API is reachable at `http://localhost:8000`.
- OpenAPI documentation: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Step 3: Tear Down

```bash
# Stop containers (preserves chunk and database volumes)
docker compose --env-file .env -f deploy/docker-compose.yml down

# Stop and wipe all data volumes
docker compose --env-file .env -f deploy/docker-compose.yml down -v
```

---

## 4. Running the 6 Required Demonstrations

An automated demonstration script is provided under `scripts/demo.py`. It showcases all 6 project requirements in sequence:

```bash
python scripts/demo.py
```

### Demonstration Scenarios Covered:

1. **Object Storage (`demo 1`)**: Uploads an arbitrary binary file and downloads it back, verifying byte-for-byte SHA-256 match.
2. **Chunking & Distribution (`demo 2`)**: Uploads a > 1 MB file (2.5 MB), verifies splitting into 1 MB chunks and fair distribution across workers.
3. **Replication (`demo 3`)**: Inspects chunk metadata to prove each chunk has exactly 2 copies residing on distinct worker nodes.
4. **Metadata Management (`demo 4`)**: Uploads custom metadata, retrieves it, and updates/patches metadata in-place via `PATCH` without re-uploading file bytes.
5. **Worker Failure & Recovery (`demo 5`)**: Simulates node crash via `docker stop worker2`, proves downloads continue seamlessly from surviving replicas, verifies health detection, and restarts `worker2` with automatic re-registration.
6. **Data Integrity & Corruption Repair (`demo 6`)**: Intentionally corrupts a chunk file on a worker's disk, attempts download to demonstrate automatic checksum mismatch detection and failover to a valid replica, followed by auto-repair of the corrupted chunk.

You can also run an individual demo by index:
```bash
python scripts/demo.py --demo 1
python scripts/demo.py --demo 5
```

---

## 5. Client CLI Usage

The interactive client CLI is located in `client/cli.py`:

```bash
# Upload an object with optional custom metadata
python -m client.cli upload ./sample.pdf --metadata '{"category":"paper","author":"Alice"}'

# List stored objects
python -m client.cli list

# View detailed object metadata & chunk distribution
python -m client.cli metadata <OBJECT_ID>

# Patch custom metadata without re-uploading
python -m client.cli patch-metadata <OBJECT_ID> '{"category":"archive","reviewed":true}'

# Download an object
python -m client.cli download <OBJECT_ID> ./downloaded_sample.pdf

# Delete an object and purge its chunks
python -m client.cli delete <OBJECT_ID>

# Inspect cluster & worker status
python -m client.cli cluster
```

---

## 6. REST API Specification

### Client API

| Method | Endpoint | Description | Success Code |
|---|---|---|---|
| `POST` | `/api/v1/objects` | Upload file (`multipart/form-data`) with optional `metadata` JSON | `201 Created` |
| `GET` | `/api/v1/objects/{object_id}` | Download complete reassembled original binary object | `200 OK` |
| `GET` | `/api/v1/objects/{object_id}/metadata` | Retrieve system & custom metadata + chunk replica locations | `200 OK` |
| `PATCH` | `/api/v1/objects/{object_id}/metadata` | Update custom metadata without re-uploading | `200 OK` |
| `DELETE` | `/api/v1/objects/{object_id}` | Delete object and all associated chunk replicas | `204 No Content` |
| `GET` | `/api/v1/objects` | List all stored objects with pagination (`offset`, `limit`) | `200 OK` |
| `GET` | `/api/v1/cluster` | Cluster health and worker node status | `200 OK` |

### Internal Worker API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/internal/workers/register` | Worker registration with controller on startup |
| `POST` | `/internal/workers/heartbeat` | Periodic worker heartbeat reporting availability and disk usage |
| `GET` | `/internal/workers/{worker_id}/chunks` | Retrieve chunk inventory stored on a worker |
| `PUT` | `/internal/chunks/{chunk_id}` | Store a chunk on a worker node |
| `GET` | `/internal/chunks/{chunk_id}` | Retrieve raw chunk bytes from a worker node |
| `DELETE` | `/internal/chunks/{chunk_id}` | Delete a chunk from a worker node |
| `POST` / `GET` | `/internal/chunks/{chunk_id}/verify` | Check chunk integrity and return SHA-256 hash |

---

## 7. Running Automated Tests

```bash
# Run test suite
python -m pytest tests/
```
