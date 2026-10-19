# CloudWeave — Mini Distributed Cloud Object Store

CloudWeave stores arbitrary binary files by splitting them into 1 MB chunks and replicating each chunk (factor 2) across four storage workers. A controller coordinates everything and keeps metadata in PostgreSQL.

> **Status:** project scaffolding. Module skeletons, configuration, Docker setup and wire models are in place; the object-storage logic is not implemented yet (unimplemented endpoints return HTTP 501).

## Architecture

```
            ┌─────────┐  REST   ┌──────────────────────┐   SQL   ┌────────────┐
  client ──▶│  CLI /  │────────▶│      controller      │────────▶│ PostgreSQL │
            │  lib    │         │ (FastAPI, metadata,  │         └────────────┘
            └─────────┘         │  placement, repair)  │
                                └──────────┬───────────┘
                          internal HTTP    │  ▲ register / heartbeat
                     ┌───────────┬─────────┼──┴────┬───────────┐
                     ▼           ▼         ▼       ▼
                  worker1     worker2   worker3  worker4   (each with its own volume)
```

- **Controller** – client REST API, object/chunk metadata, chunking and reassembly, worker registry and health monitoring, chunk placement, replication, checksum verification and repair, deletion.
- **Worker** – stores chunks on local persistent disk, serves/deletes/verifies chunks by ID, registers with the controller, sends heartbeats and reports stored chunks. Workers never touch the database; all communication uses internal HTTP APIs under `/internal`.
- **Shared** – constants, wire models and exceptions imported by both services.

All four workers run the **same image**; identity comes from environment variables (`WORKER_ID`, `ADVERTISE_URL`) and each gets its own named volume.

## Folder responsibilities

| Path | Purpose |
|------|---------|
| `controller/app/api` | HTTP routers only (objects, metadata, internal worker endpoints) |
| `controller/app/services` | Business logic (objects, chunks, metadata, worker HTTP client) |
| `controller/app/repositories` | All database queries |
| `controller/app/db` | Engine/session, declarative base, ORM models |
| `controller/app/schemas` | Pydantic request/response schemas |
| `controller/app/scheduler` | Chunk placement and replication |
| `controller/app/cluster` | Worker registry and heartbeat health monitor |
| `controller/app/integrity` | Checksums and replica repair |
| `controller/app/core` | Settings, logging, exceptions |
| `worker/app/api` | Chunk and worker endpoints |
| `worker/app/storage` | Local chunk store |
| `worker/app/heartbeat` | Registration and heartbeat reporter |
| `worker/app/integrity` | Checksum utilities |
| `shared/` | Code shared by controller, worker and client |
| `client/` | Python client library and CLI |
| `deploy/` | Docker Compose configuration |
| `tests/` | Integration, failure-recovery and data-integrity tests |
| `scripts/`, `docs/` | Helper scripts and documentation |

### Import paths

Both services use a top-level `app` package and import `shared.*`. In Docker, the build context is the repo root and `PYTHONPATH=/app` with `shared/` and `app/` copied side by side. Locally, run a service from its directory with the repo root on `PYTHONPATH`.

## Prerequisites

- Docker and Docker Compose v2
- Python 3.12+ (only for local development)
- `make` (optional; the raw `docker compose` commands are shown below)

## Startup

```bash
cp .env.example .env          # then edit the placeholder values
make up                       # build and start postgres, controller, worker1-4
make logs                     # follow logs
make down                     # stop (volumes are kept)
make clean                    # stop and delete volumes
```

Without make:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

The controller listens on `http://localhost:8000` (`/docs` for the OpenAPI UI, `/health` for liveness).

### Local development (no Docker)

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# controller (needs a reachable PostgreSQL via DATABASE_URL)
cd controller && PYTHONPATH=..  uvicorn app.main:app --port 8000
# worker
cd worker && PYTHONPATH=.. WORKER_ID=worker1 STORAGE_DIR=./data uvicorn app.main:app --port 8001
# client
python -m client.cli --help
```

## Implemented vs. still to do

**Scaffolded (present):** FastAPI apps and routers, settings, DB models and session, schemas, shared wire models, checksum helpers, internal-token check, Dockerfiles, Compose with 4 workers + volumes, Makefile, client/CLI shells.

**To implement:** repository queries, chunk splitting/upload/download/delete flow, worker `ChunkStore` and verify endpoint, worker registration and heartbeat loop, health monitor, placement strategy, replication and re-replication, integrity repair, migrations (Alembic), and all tests.
