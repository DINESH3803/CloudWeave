# CloudWeave: Mini Distributed Cloud Object Store
## Project Technical Report

---

### Project Information

- **Project Title:** CloudWeave — A Fault-Tolerant Mini Distributed Cloud Object Store
- **Architecture Model:** 1 Controller Node, 4 Persistent Storage Workers, 1 PostgreSQL Metadata Database
- **Submission Components:** Comprehensive Technical Report, Source Codebase, Demonstration Test Suite

### Team Members

1. **Amballa Pardhiv** (Roll No: `BT2024071`)
2. **Chevuru V R Dinesh Karthik** (Roll No: `BT2024199`)

---

## Executive Summary

**CloudWeave** is a resilient, fault-tolerant distributed object store designed to store, manage, and retrieve arbitrary binary objects (such as images, video, documents, and archives). The system decomposes uploaded files into bounded **1 MB chunks**, computes cryptographic hashes (SHA-256) for end-to-end integrity, and distributes chunk replicas across a cluster of independent storage worker nodes while strictly enforcing a **replication factor of 2**.

The platform is designed with a decoupled architecture where the **Controller** manages object metadata, chunk placement scheduling, background health monitoring, and data healing, while **Workers** operate as lightweight, isolated HTTP storage daemons that read and write chunks directly to persistent disk volumes. The system guarantees high availability and durability through:
1. **Dynamic Chunk Placement:** Least-loaded worker scheduling ensuring disjoint replica storage.
2. **Seamless Object Reassembly:** Transparent streaming download with client abstraction from worker topologies.
3. **In-Place Custom Metadata Management:** Fast JSON metadata updates without file re-uploading.
4. **Failure Detection & Failover:** Automatic node timeout detection via heartbeats and failover to surviving replicas.
5. **Data Self-Healing:** Checksum verification on every read with automatic bitrot detection and replica repair.

---

## 1. System Architecture & Topology

CloudWeave is deployed as a multi-container Docker cluster comprising one centralized Controller, four independent Storage Workers (`worker1`, `worker2`, `worker3`, `worker4`), and a dedicated PostgreSQL relational database for transactional metadata storage.

### High-Level Architecture Diagram

```text
                     +----------------------------------+
                     |       Client CLI / SDK           |
                     |  (REST API: /api/v1/objects)     |
                     +-----------------+----------------+
                                       |
                                       | HTTP (Multipart / Streaming)
                                       v
                     +----------------------------------+
                     |       CloudWeave Controller      |
                     |  (FastAPI, Placement, Repair,   |
                     |   Health Monitor, Auth Token)    |
                     +-------+--------------------+-----+
                             |                    |
            PostgreSQL (SQL) |                    | Internal HTTP (X-Internal-Token)
            Port: 5432       |                    | Ports: 8001
                             v                    |
                 +--------------------+           |
                 | PostgreSQL Metadata|           |
                 | (Objects, Chunks,  |           |
                 |  Replicas, Workers)|           |
                 +--------------------+           |
                                                  |
         +--------------------+-------------------+--------------------+
         |                    |                   |                    |
         v                    v                   v                    v
  +--------------+     +--------------+    +--------------+     +--------------+
  |   worker1    |     |   worker2    |    |   worker3    |     |   worker4    |
  |  Port: 8001  |     |  Port: 8001  |    |  Port: 8001  |     |  Port: 8001  |
  | Volume: data |     | Volume: data |    | Volume: data |     | Volume: data |
  +--------------+     +--------------+    +--------------+     +--------------+
```

### Component Roles & Responsibilities

1. **Client Application (`client/`):**
   - Interacts exclusively with the controller via public REST endpoints.
   - Streams uploads, issues downloads, updates metadata, and inspects cluster status without any knowledge of internal worker topology or chunk placements.

2. **Controller Service (`controller/`):**
   - Acts as the cluster orchestrator, API gateway, and metadata manager.
   - Splits incoming file streams into 1 MB chunks, computes cryptographic digests, and coordinates parallel replica uploads.
   - Manages relational state in PostgreSQL using SQLAlchemy ORM.
   - Runs a background `HealthMonitor` thread to detect unresponsive worker nodes and trigger under-replication repair.
   - Automatically repairs corrupted chunks upon read detection using intact replicas.

3. **Storage Workers (`worker/`):**
   - Four distinct container instances (`worker1` to `worker4`) built from a single unified Dockerfile.
   - Execute an isolated FastAPI web service serving internal chunk management routes (`/internal/chunks`).
   - Store chunks as raw binary files on independent persistent volumes mounted at `/data/chunks`.
   - Never interact directly with the PostgreSQL database.
   - Register on startup and send periodic heartbeat pings (every 5 seconds) to report disk usage and chunk inventories.

4. **Metadata Store (`PostgreSQL 16`):**
   - Stores ACID-compliant relational schemas for objects, chunks, worker nodes, and replica mappings.
   - Stores custom key-value metadata in JSON format, enabling flexible querying and zero-reupload metadata updates.

---

## 2. Directory Structure & Code Organization

The repository is organized into distinct, modular packages with clear boundary separations:

```text
CloudWeave (Repository Root)
|-- controller/                 Controller Service Implementation
|   |-- app/
|   |   |-- main.py             Lifespan startup/shutdown, router registration, /health
|   |   |-- api/                HTTP route handlers
|   |   |   |-- objects.py      Public REST API: upload, download, list, metadata, delete
|   |   |   |-- metadata.py     Cluster status and object metadata inspection
|   |   |   `-- internal_workers.py  Worker registration, heartbeat, and chunk inventory
|   |   |-- core/               Configuration, logging, and HTTP error mappings
|   |   |-- db/                 Database base, session lifecycle, and ORM models
|   |   |-- schemas/            Pydantic input/output validation schemas
|   |   |-- repositories/       Encapsulated SQL database queries
|   |   |-- services/           Core business logic (chunking, streaming, auto-repair)
|   |   |-- scheduler/          Placement algorithms and replication management
|   |   |-- cluster/            Worker registry and background health monitoring loop
|   |   `-- integrity/          Cryptographic hashing and replica healing
|   |-- Dockerfile              Controller image specification
|   `-- requirements.txt        Controller Python dependencies
|-- worker/                     Storage Worker Service Implementation
|   |-- app/
|   |   |-- main.py             Worker lifespan, local storage initialization, API mounting
|   |   |-- api/                Internal chunk storage endpoints (PUT/GET/DELETE/verify)
|   |   |-- core/               Worker configuration loaded from environment variables
|   |   |-- storage/            Atomic filesystem persistence and path traversal protection
|   |   |-- heartbeat/          Background registration and recurring heartbeat pings
|   |   `-- integrity/          SHA-256 validation utilities
|   |-- Dockerfile              Worker container specification
|   `-- requirements.txt        Worker Python dependencies
|-- shared/                     Common Shared Module
|   |-- constants.py            Global constants (1 MB chunk size, replication factor 2)
|   |-- exceptions.py           Domain error hierarchy mapped to HTTP status codes
|   `-- models.py               Pydantic wire models for inter-service communication
|-- client/                     Client SDK & CLI Utility
|   |-- client.py               Python programmatic client (`CloudWeaveClient`)
|   |-- cli.py                  Command-line interface (`upload`, `download`, `list`, etc.)
|   `-- requirements.txt        Client dependencies
|-- deploy/                     Container Orchestration
|   |-- docker-compose.yml      Full stack definition (postgres, controller, worker1-4)
|   `-- .env                    Configured environment variables
|-- scripts/                    Operational & Demonstration Scripts
|   `-- demo.py                 Automated test runner executing all 6 demonstration scenarios
|-- tests/                      Automated Test Suites
|   |-- conftest.py             Test fixtures and environment configuration
|   |-- integration/            End-to-end API roundtrip tests
|   |-- data_integrity/         Chunk splitting and hashing validation tests
|   `-- failure_recovery/       Scheduler placement and failover tests
|-- docs/                       Documentation and Technical Reports
|-- Makefile                    Make automation targets for building and testing
`-- README.md                   Quickstart and operational deployment guide
```

---

## 3. Core Mechanisms & Design Implementation

### 3.1 1 MB Chunking and Stream Processing
- When an object is uploaded via `POST /api/v1/objects`, the controller reads the binary stream in fixed chunks of `1,048,576 bytes` (`1 MB`).
- The last chunk takes any remaining bytes (ranging from 1 byte to 1 MB).
- Each chunk is assigned a deterministic identifier formatted as `<object_id>_<chunk_index>`.
- The controller computes individual SHA-256 hashes for each chunk as well as a cumulative composite hash for the entire object.

### 3.2 Dynamic Replica Placement & Storage
- CloudWeave enforces a strict **replication factor of 2**.
- The `LeastLoadedPlacement` algorithm calculates candidate nodes using a two-step policy:
  1. **Disjoint Worker Constraint:** Replicas for the same chunk are always placed on distinct worker nodes. A chunk's primary and secondary copies will never reside on the same worker.
  2. **Load Balancing:** Workers with the lowest cumulative disk usage (`used_bytes`) are prioritized. A round-robin offset based on `chunk_index` interleaves assignments among workers that share equal storage load.

### 3.3 Transparent Object Reassembly
- When a client requests `GET /api/v1/objects/{object_id}`, the controller looks up the ordered chunk list from the database.
- It sequentially contacts the assigned workers, streams each chunk, and delivers a unified HTTP `StreamingResponse` back to the client.
- The client receives the complete original binary file without ever having to manage chunk indices, locations, or socket connections to individual workers.

### 3.4 Custom Metadata & In-Place Modification
- The system supports arbitrary user-defined metadata (e.g., author, project, environment, classification tags) passed as a JSON object during upload.
- Custom metadata is stored in PostgreSQL as a structured `JSON` column on the `objects` table.
- Clients can view metadata via `GET /api/v1/objects/{object_id}/metadata`.
- Clients can modify metadata via `PATCH /api/v1/objects/{object_id}/metadata`. The controller merges new key-values and deletes keys mapped to `None` in-place, updating the `updated_at` timestamp **without touching, re-uploading, or invalidating the stored chunk files on worker nodes**.

### 3.5 Worker Failure Detection and Recovery
- Workers send periodic heartbeat pings (`POST /internal/workers/heartbeat`) every **5 seconds**.
- The controller runs an asynchronous background `HealthMonitor` loop:
  - If a worker misses heartbeats for more than **15 seconds** (`heartbeat_timeout_seconds`), the controller flags its status as `unhealthy`.
  - The controller automatically executes `restore_replication()`, querying for any chunks that now have fewer than 2 active replicas.
  - For each under-replicated chunk, the controller retrieves valid data from the surviving healthy replica and writes a new replica to another available worker, restoring the required replication factor of 2.
- When the stopped worker restarts, it sends an initial registration payload (`POST /internal/workers/register`) reporting its local chunk inventory. The controller reconciles the database records, transitioning the worker back to `active`.

### 3.6 Data Integrity, Bitrot Protection, and Self-Healing
- **Write Verification:** Every chunk stored on a worker is written to a temporary file, flushed with `os.fsync()`, and atomically renamed to guarantee durability against sudden power failures.
- **Read Verification:** Whenever the controller reads a chunk to satisfy a download request, it computes the SHA-256 hash of the received bytes and compares it against the expected hash recorded in the database.
- **Failover & Auto-Repair:**
  - If a worker returns corrupted data (or fails with an HTTP error), the controller immediately logs a warning, marks that replica as `corrupt`, and fails over to the second replica copy.
  - The controller serves the valid replica data to the client so that client downloads succeed without error.
  - The controller immediately repairs the corrupted worker replica by pushing the valid bytes back to the affected worker and marking the replica status as `stored`.

---

## 4. API Specifications & Status Code Mappings

### 4.1 Client REST API

| Method | Endpoint | Description | Success Status | Error Statuses |
|---|---|---|---|---|
| `POST` | `/api/v1/objects` | Upload file stream and optional JSON metadata | `201 Created` | `400`, `500`, `503` |
| `GET` | `/api/v1/objects` | Paginated listing of stored objects | `200 OK` | `500` |
| `GET` | `/api/v1/objects/{id}` | Download and reassemble object binary stream | `200 OK` | `404`, `500`, `503` |
| `GET` | `/api/v1/objects/{id}/metadata` | Retrieve complete object & chunk replica metadata | `200 OK` | `404`, `500` |
| `PATCH` | `/api/v1/objects/{id}/metadata` | In-place update of custom metadata dictionary | `200 OK` | `400`, `404`, `500` |
| `DELETE` | `/api/v1/objects/{id}` | Delete object and cascade delete chunk replicas | `204 No Content` | `404`, `500` |
| `GET` | `/api/v1/cluster` | Query cluster status, workers, and configurations | `200 OK` | `500` |

### 4.2 Internal Worker API (Authenticated via `X-Internal-Token`)

| Method | Endpoint | Description | Success Status |
|---|---|---|---|
| `POST` | `/internal/workers/register` | Register worker address and reconcile chunk inventory | `200 OK` |
| `POST` | `/internal/workers/heartbeat` | Periodic worker ping reporting used disk space | `204 No Content` |
| `PUT` | `/internal/chunks/{chunk_id}` | Store raw chunk binary file on worker disk | `204 No Content` |
| `GET` | `/internal/chunks/{chunk_id}` | Retrieve raw chunk binary stream | `200 OK` |
| `DELETE` | `/internal/chunks/{chunk_id}` | Delete chunk file from worker disk | `204 No Content` |
| `POST` | `/internal/chunks/{chunk_id}/verify` | Verify chunk file existence and return SHA-256 hash | `200 OK` |
| `GET` | `/internal/workers/{id}/chunks` | Return list of chunks stored on a specific worker | `200 OK` |

### 4.3 HTTP Status Code Mapping Reference

| Status Code | Reason / Meaning | Triggering Condition |
|---|---|---|
| `200 OK` | Request succeeded | Successful download, listing, metadata retrieval, or patch |
| `201 Created` | Resource created | Successful object upload and chunk distribution |
| `204 No Content` | Successful operation with no body | Successful object deletion or worker heartbeat |
| `400 Bad Request` | Malformed input | Invalid JSON metadata or bad request payload |
| `404 Not Found` | Resource missing | Object or chunk ID not found in database or disk |
| `409 Conflict` | State conflict | Concurrent upload or invalid state transition |
| `500 Internal Error` | Data corruption / server fault | Unrecoverable checksum mismatch or system error |
| `503 Service Unavailable` | Cluster unavailable | Insufficient healthy workers to satisfy replication factor |

---

## 5. Verification & Demonstration Results

To ensure compliance with the project specifications, the entire platform was verified through automated end-to-end demonstrations executed against a live Docker Compose cluster using `scripts/demo.py`. All 6 required demonstration scenarios executed and passed with 100% verification.

### Summary of Demonstration Scenarios

```text
======================================================================
 CloudWeave Mini Distributed Cloud Object Store -- Demonstration Suite
 Target Controller: http://localhost:8000
 Cluster Health: 4 Active Workers (worker1, worker2, worker3, worker4)
======================================================================
```

#### Demo 1: Object Storage (Upload & Retrieve Verification)
- **Procedure:** Generated a random 500 KB binary payload, uploaded it to the cluster via `POST /api/v1/objects`, retrieved it via `GET /api/v1/objects/{id}`, and computed SHA-256 hashes of both streams.
- **Result:**
  - Original SHA-256: `1c70b280ad8ea9d2f8704c2ea533daf21421cf4c73f16be4b161f2e5552cc919`
  - Downloaded SHA-256: `1c70b280ad8ea9d2f8704c2ea533daf21421cf4c73f16be4b161f2e5552cc919`
  - **Verdict:** PASSED. Downloaded object is byte-for-byte identical to the original.

#### Demo 2: Chunking & Distribution (>1 MB File Split Across Workers)
- **Procedure:** Created a 2.5 MB (`2,621,440 bytes`) test payload exceeding the 1 MB boundary and uploaded it to the cluster.
- **Result:**
  - Chunk 0: Size = 1,048,576 bytes (1.0 MB), stored on `worker3` and `worker4`.
  - Chunk 1: Size = 1,048,576 bytes (1.0 MB), stored on `worker1` and `worker2`.
  - Chunk 2: Size = 524,288 bytes (0.5 MB), stored on `worker3` and `worker4`.
  - Reassembly Check: Retrieved object matched original SHA-256 digest.
  - **Verdict:** PASSED. The 2.5 MB file was cleanly split into three 1 MB-bounded chunks and distributed across workers.

#### Demo 3: Replication (Replication Factor 2 Across Distinct Workers)
- **Procedure:** Inspected replica assignments for all chunks in the object store.
- **Result:**
  - Every chunk has exactly 2 replica entries stored in the database.
  - For every chunk, the primary and secondary replica reside on completely distinct worker nodes (e.g., `['worker1', 'worker2']`).
  - **Verdict:** PASSED. Replication factor of 2 is strictly maintained across distinct nodes.

#### Demo 4: Metadata (Retrieval & Patching Without Re-upload)
- **Procedure:** Uploaded an object with metadata `{"author": "Alice", "project": "CloudWeave", "environment": "dev"}`. Patched the object with `{"environment": "production", "version": "v2.0", "reviewer": "Bob"}` without re-uploading file bytes.
- **Result:**
  - Metadata was updated in-place on PostgreSQL.
  - New fields were added, specified fields were modified, and original fields were preserved:
    `{"author": "Alice", "project": "CloudWeave", "environment": "production", "version": "v2.0", "reviewer": "Bob"}`
  - Subsequent download verified that underlying chunk bytes remained unaltered.
  - **Verdict:** PASSED. Metadata was patched in-place with zero chunk re-transfers.

#### Demo 5: Worker Failure & Recovery
- **Procedure:** Uploaded a multi-chunk object stored across workers. Simulated a catastrophic node failure by stopping the replica host container using `docker stop worker3`. Downloaded the object while the worker remained offline. Restarted the container using `docker start worker3`.
- **Result:**
  - Object download succeeded with 100% hash fidelity while `worker3` was offline by failing over to surviving replica `worker4`.
  - Upon executing `docker start worker3`, the worker re-registered within 4 seconds.
  - Replication check verified that all chunks maintained their required 2 stored replicas.
  - **Verdict:** PASSED. The system tolerated node failure, maintained service availability, and recovered full replication health upon restart.

#### Demo 6: Data Integrity & Bitrot Repair
- **Procedure:** Uploaded a chunk stored on `worker1` and `worker2`. Intentionally corrupted the physical chunk file on `worker1` by writing garbage bytes:
  `docker exec worker1 sh -c "echo 'CORRUPTED_BYTES_HERE' > /data/chunks/<chunk_id>"`
  Requested object download through the controller.
- **Result:**
  - The controller computed the hash upon reading from `worker1`, detected a checksum mismatch, and logged a corruption warning.
  - The controller avoided returning bad bytes, immediately failed over to `worker2`, and returned the valid object to the client.
  - The controller automatically healed `worker1` by copying valid bytes from `worker2` and restored replica status to `stored`.
  - **Verdict:** PASSED. Corrupted data was auto-detected, rejected, and self-healed.

---

## 6. Deployment and Operational Instructions

### 6.1 Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+
- Python 3.10+ (for running the CLI or demonstration script from host)

### 6.2 Cluster Deployment

```bash
# 1. Clone repository and navigate to root
cd CloudWeave

# 2. Build images and start all 6 containers in detached mode
docker compose --env-file .env -f deploy/docker-compose.yml up --build -d

# 3. Verify running containers (controller, postgres, worker1-4)
docker ps
```

### 6.3 Executing the Automated Demonstration Suite

```bash
# Run all 6 demonstration scenarios sequentially
python scripts/demo.py

# Or run any individual demonstration scenario (e.g., scenario 5)
python scripts/demo.py --demo 5
```

### 6.4 Client CLI Usage Examples

```bash
# Check cluster health and active workers
python -m client.cli cluster

# Upload a file with custom metadata
python -m client.cli upload sample.pdf --metadata '{"author": "Pardhiv", "category": "report"}'

# List all stored objects
python -m client.cli list

# View full metadata and chunk replica distribution for an object
python -m client.cli metadata <OBJECT_ID>

# Patch metadata without re-uploading file
python -m client.cli patch-metadata <OBJECT_ID> '{"status": "finalized", "reviewer": "Dinesh"}'

# Download and reassemble object
python -m client.cli download <OBJECT_ID> output.pdf

# Delete object and cascade purge chunks across workers
python -m client.cli delete <OBJECT_ID>
```

### 6.5 Running Automated Unit & Integration Tests

```bash
# Execute full test suite via pytest
python -m pytest tests/
```

---

## 7. Conclusion

CloudWeave successfully fulfills all functional, architectural, and reliability requirements specified for a distributed cloud object store:
- **Decoupled Architecture:** Clean separation of concerns where workers handle disk I/O and the controller handles cluster intelligence and metadata.
- **High Durability:** 1 MB chunking combined with replication factor 2 and disjoint node placement guarantees file survival across worker outages.
- **Zero Client Overhead:** Clients interact through standard REST endpoints without needing awareness of chunk boundaries, worker addresses, or failure failovers.
- **Active Self-Healing:** The combination of heartbeat monitoring and checksum verification on read guarantees automatic bitrot detection, dynamic failover, and automated replica healing.

The codebase is structured, fully commented, containerized, and ready for deployment and evaluation.
