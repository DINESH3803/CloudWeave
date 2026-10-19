# CloudWeave — Mini Distributed Cloud Object Store

**Project notebook and checklist.** Updated by hand. Last updated: 2026-10-20 (initial assessment of the repository).

## Progress Summary (manually maintained)

Counts reflect the initial assessment on 2026-10-20. Update these numbers yourself when you change task statuses.

| Phase | Tasks completed | Subtasks completed |
|---|---|---|
| 0 — Repository Setup and Architecture | 6 / 11 | 20 / 30 |
| 1 — Worker Storage | 1 / 10 | 5 / 30 |
| 2 — Database and Metadata | 0 / 10 | 0 / 26 |
| 3 — Chunking and Object Storage | 0 / 7 | 0 / 25 |
| 4 — Distribution and Replication | 0 / 7 | 0 / 21 |
| 5 — Client REST APIs | 0 / 8 | 0 / 27 |
| 6 — Worker Failure Recovery | 0 / 7 | 0 / 27 |
| 7 — Data Integrity | 0 / 7 | 0 / 16 |
| 8 — Client and Documentation | 0 / 5 | 0 / 13 |
| 9 — Testing | 0 / 8 | 0 / 21 |
| 10 — Final Demonstration | 0 / 9 | 0 / 22 |
| **Total** | **7 / 89** | **25 / 258 (about 9.7%)** |

Parent task status right now: 7 `COMPLETED`, 16 `IN PROGRESS`, 66 `NOT STARTED`, 0 `BLOCKED`, 0 `DEFERRED`.

**Honest state of the project:** the folder structure, configuration, Docker files and module skeletons exist and were checked for imports and Compose parsing. No storage functionality is implemented. Docker images have not been built, the stack has not been started, PostgreSQL has not been used and there are no automated tests.

Status values: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `COMPLETED`, `DEFERRED`. A box is `[x]` only when the status is `COMPLETED`.

---

## 1. Project Overview

**CloudWeave** is a mini distributed cloud object store. Clients upload arbitrary binary objects (documents, images, video, audio, archives). The controller splits each object into 1 MB chunks, stores every chunk on two different workers, and keeps all metadata in PostgreSQL. The system detects worker failures, keeps serving data from surviving replicas, restores the replication factor, and uses checksums to detect and repair corrupted chunks.

**Technology stack**

- Python 3.12 and FastAPI
- One Controller service
- Four Storage Worker instances (`worker1` to `worker4`, one image, per-instance environment variables)
- PostgreSQL for metadata (SQLAlchemy 2)
- Docker and Docker Compose (no Kubernetes)
- 1 MB chunks, replication factor 2, persistent storage for every worker

**Required behaviour (from the assignment spec, `Mini_Distributed_Cloud_Object_Store.pdf`)**

- Upload and download binary objects with a unique Object ID.
- Keep object name, size, content type, created and last-modified time, checksum, chunk count, chunk info and locations, and custom key-value metadata.
- Chunk size 1 MB (last chunk may be smaller), unique chunk IDs, order preserved.
- Two copies of each chunk on different workers, spread across workers; detect and restore lost replication.
- Client REST API: `POST /api/v1/objects`, `GET /api/v1/objects/{object_id}`, `GET /api/v1/objects/{object_id}/metadata`, `PATCH /api/v1/objects/{object_id}/metadata`, `DELETE /api/v1/objects/{object_id}`, `GET /api/v1/objects`. Success codes 201, 200, 200, 200, 204, 200. Errors use 400, 404, 409, 500, 503 with a JSON message.
- Internal APIs: `POST /internal/workers/register`, `POST /internal/workers/heartbeat`, `PUT/GET/DELETE /internal/chunks/{chunk_id}`, `GET /internal/workers/{worker_id}/chunks`.
- Survive a worker failure (`docker stop worker2`, `docker start worker2`) and demonstrate behaviour before, during and after.
- Detect corrupted data, avoid returning it when a valid copy exists, repair where possible, and demonstrate with intentional corruption.
- Runnable locally with Docker; instructions for building, starting and using the system.

**Constraints:** controller and worker stay separate applications; workers never access the database; no database logic in route handlers; no per-worker code copies; configuration only through environment variables with a placeholder-only `.env.example`.

### Working agreement for future development

Whenever you ask an assistant to implement or debug a task:

1. It reads this file first and identifies the relevant task IDs.
2. It implements only the requested functionality and tests it when possible.
3. It tells you which task IDs were implemented and what remains unfinished.
4. It does **not** change statuses or checkboxes in this file. You update them yourself.
5. It does not regenerate, overwrite or simplify this notebook.

No script or automation is used to maintain this file.

---

## 2. Architecture and Folder Structure

```text
CloudWeave (repository root)
├── controller/            FastAPI controller service
│   ├── app/
│   │   ├── main.py        app factory, lifespan, /health
│   │   ├── api/           routers only: objects.py, metadata.py, internal_workers.py
│   │   ├── core/          config.py, logging.py, exceptions.py
│   │   ├── db/            base.py, session.py, models.py
│   │   ├── schemas/       objects.py, metadata.py, workers.py
│   │   ├── repositories/  object_, chunk_, worker_repository.py (all DB queries)
│   │   ├── services/      object_, chunk_, metadata_service.py, worker_client.py
│   │   ├── scheduler/     placement.py, replication.py
│   │   ├── cluster/       registry.py, health_monitor.py
│   │   └── integrity/     checksum.py, repair.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── worker/                FastAPI storage worker (one codebase, four instances)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/           chunks.py, worker.py
│   │   ├── core/          config.py
│   │   ├── storage/       chunk_store.py
│   │   ├── integrity/     checksum.py
│   │   └── heartbeat/     reporter.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── shared/                constants.py, models.py, exceptions.py (used by both services)
├── client/                client.py (Python client), cli.py, requirements.txt
├── tests/                 integration/, failure_recovery/, data_integrity/
├── deploy/                docker-compose.yml (postgres, controller, worker1-4, volumes)
├── scripts/               demonstration and development utilities (empty for now)
├── docs/                  architecture, API docs, demo evidence (empty for now)
├── .env.example  .gitignore  .dockerignore  Makefile  requirements.txt  README.md
└── CloudWeave.md          this notebook
```

**Communication:** clients talk to the controller over REST. The controller talks to workers over internal HTTP under `/internal`. Workers register and send heartbeats to the controller. Only the controller talks to PostgreSQL.

**Import paths:** both services have a top-level `app` package and import `shared.*`. In Docker the build context is the repository root with `PYTHONPATH=/app`. Locally, run a service from its own directory with the repository root on `PYTHONPATH`.

---

## 3. Overall Task Checklist

One line per phase. Tick a phase when every task in it is `COMPLETED`.

- [ ] **Phase 0 — Repository Setup and Architecture** — Status: IN PROGRESS
- [ ] **Phase 1 — Worker Storage** — Status: IN PROGRESS
- [ ] **Phase 2 — Database and Metadata** — Status: IN PROGRESS
- [ ] **Phase 3 — Chunking and Object Storage** — Status: IN PROGRESS
- [ ] **Phase 4 — Distribution and Replication** — Status: NOT STARTED
- [ ] **Phase 5 — Client REST APIs** — Status: NOT STARTED
- [ ] **Phase 6 — Worker Failure Recovery** — Status: NOT STARTED
- [ ] **Phase 7 — Data Integrity** — Status: NOT STARTED
- [ ] **Phase 8 — Client and Documentation** — Status: NOT STARTED
- [ ] **Phase 9 — Testing** — Status: NOT STARTED
- [ ] **Phase 10 — Final Demonstration** — Status: NOT STARTED

---

## 4. Phase-by-Phase Tasks and Subtasks

Task IDs are `CW-nnn`; subtasks are `CW-nnn.m`. IDs are stable: never renumber or reuse them; add new items with the next free number. Subtasks inherit the task's priority and may list extra dependencies. Evidence for completed work is recorded in each task's Notes; only checks that were actually run are listed.

### Phase 0: Repository Setup and Architecture

- [x] **CW-001: Inspect existing repository and assignment spec**
  - Status: COMPLETED
  - Priority: HIGH
  - Description: Inventory the starting repository and extract requirements from the spec PDF.
  - Acceptance criteria: Starting state and spec requirements are known and recorded.
  - Verification: Review this notebook against the PDF.
  - Notes: At the start the repo had only empty `client/`, `controller/`, `deploy/`, `shared/`, `tests/`, `worker/`, a `venv/` and the spec PDF. The PDF (3 pages) was read in full.
  - Subtasks:
    - [x] **CW-001.1** Inspect existing folders and files — Status: COMPLETED
    - [x] **CW-001.2** Read the spec PDF and capture requirements (Section 1) — Status: COMPLETED

- [x] **CW-002: Complete the folder structure**
  - Status: COMPLETED
  - Priority: HIGH
  - Depends on: CW-001
  - Description: Create every directory and file in the agreed architecture.
  - Acceptance criteria: All paths in Section 2 exist; `__init__.py` files are present in packages.
  - Verification: Recursive directory listing.
  - Notes: Verified by listing on 2026-10-20. Also added `.dockerignore` and `.gitkeep` placeholders in empty directories.
  - Subtasks:
    - [x] **CW-002.1** Create `controller/` and `worker/` package trees — Status: COMPLETED
    - [x] **CW-002.2** Create `shared/`, `client/`, `tests/`, `deploy/`, `scripts/`, `docs/` — Status: COMPLETED
    - [x] **CW-002.3** Create root files (`.env.example`, `.gitignore`, `.dockerignore`, `Makefile`, `requirements.txt`, `README.md`) — Status: COMPLETED

- [x] **CW-003: Controller and worker application scaffolding**
  - Status: COMPLETED
  - Priority: HIGH
  - Depends on: CW-002
  - Description: FastAPI entry points, routers and typed module skeletons for both services.
  - Acceptance criteria: Both apps import, routers are registered, skeletons fail with HTTP 501 rather than pretending to work.
  - Verification: Import both apps, list OpenAPI paths, call a skeleton route.
  - Notes: Verified 2026-10-20: controller OpenAPI paths are `/health`, `/internal/workers`, `/internal/workers/heartbeat`, `/internal/workers/register`, `/metadata/cluster`, `/metadata/objects/{object_id}`, `/objects`, `/objects/{object_id}`. Worker `/health` returns ok. Skeletons raise `NotImplementedError` (HTTP 501). **Scaffolding is not functionality.**
  - Subtasks:
    - [x] **CW-003.1** Controller app factory with objects, metadata and internal routers — Status: COMPLETED
    - [x] **CW-003.2** Worker app factory with chunk and worker routers — Status: COMPLETED
    - [x] **CW-003.3** Typed skeletons for services, repositories, scheduler, cluster, integrity, storage, heartbeat — Status: COMPLETED

- [x] **CW-004: Shared package**
  - Status: COMPLETED
  - Priority: HIGH
  - Depends on: CW-002
  - Description: Shared constants, wire models and exceptions used by controller, worker and client.
  - Acceptance criteria: `shared.*` imports in controller, worker and client.
  - Verification: Import from each service with the repo root on `PYTHONPATH`.
  - Notes: Verified locally on 2026-10-20. Image-level check is CW-007.3.
  - Subtasks:
    - [x] **CW-004.1** Define `constants.py`, `models.py`, `exceptions.py` — Status: COMPLETED
    - [x] **CW-004.2** Make `shared` importable by both services (`PYTHONPATH` and Docker build context) — Status: COMPLETED

- [ ] **CW-005: Configure dependencies**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-002
  - Description: Minimal compatible dependencies per service plus a root file for local development.
  - Acceptance criteria: `pip install` works locally and inside each image.
  - Verification: `pip install -r requirements.txt` in the venv; Docker image builds.
  - Notes: Local install succeeded on 2026-10-20 (fastapi 0.149.0, httpx 0.28.1, psycopg2-binary 2.9.13, pydantic 2.14.1, pydantic-settings 2.16.0, SQLAlchemy 2.0.55). Image installs are unverified.
  - Subtasks:
    - [x] **CW-005.1** Per-service `requirements.txt` (controller, worker, client) — Status: COMPLETED
    - [x] **CW-005.2** Root `requirements.txt` for local development (includes pytest) — Status: COMPLETED
    - [ ] **CW-005.3** Per-service requirements suffice in clean Docker images — Status: NOT STARTED — Depends on: CW-007.1, CW-007.2

- [ ] **CW-006: Configure environment variables**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-002
  - Description: All tunables come from environment variables; `.env.example` has placeholders only.
  - Acceptance criteria: Settings override from the environment; no real secrets in the repo; values reach containers.
  - Verification: Set variables and read settings; `docker compose exec <service> env`.
  - Notes: Verified 2026-10-20 locally: controller read `REPLICATION_FACTOR=3`, `HEARTBEAT_TIMEOUT_SECONDS=99`; worker read `WORKER_ID=workerZ`, `HEARTBEAT_INTERVAL_SECONDS=7`. `.env.example` reviewed by eye (placeholders only).
  - Subtasks:
    - [x] **CW-006.1** Controller and worker settings classes read environment variables — Status: COMPLETED
    - [x] **CW-006.2** `.env.example` with placeholder values only — Status: COMPLETED
    - [ ] **CW-006.3** Environment values reach running containers — Status: NOT STARTED — Depends on: CW-008.2

- [ ] **CW-007: Create Dockerfiles**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003, CW-005
  - Description: One Dockerfile per service, built from the repository root so `shared/` is included.
  - Acceptance criteria: Both images build and can import `app` and `shared`.
  - Verification: `docker compose --env-file .env.example -f deploy/docker-compose.yml build`; `docker run --rm <image> python -c "import app.main, shared.models"`.
  - Notes: Dockerfiles are written but never built. Docker daemon availability has not been confirmed (only `docker compose config` was run).
  - Subtasks:
    - [ ] **CW-007.1** Controller image builds — Status: IN PROGRESS — Next: build the controller image
    - [ ] **CW-007.2** Worker image builds — Status: IN PROGRESS — Next: build the worker image
    - [ ] **CW-007.3** Both images import `app` and `shared` at runtime — Status: NOT STARTED — Depends on: CW-007.1, CW-007.2

- [ ] **CW-008: Create Docker Compose configuration**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-002
  - Description: PostgreSQL, one controller, `worker1` to `worker4`, persistent volumes.
  - Acceptance criteria: Stack starts; controller starts after PostgreSQL is healthy.
  - Verification: `docker compose config`; `docker compose up -d`; `docker compose ps`.
  - Notes: `docker compose --env-file .env.example -f deploy/docker-compose.yml config` exited 0 on 2026-10-20 and showed `worker1`-`worker4` with `WORKER_ID` worker1..worker4, volumes `worker1_data`..`worker4_data` and controller port 8000. Nothing was built or started.
  - Subtasks:
    - [x] **CW-008.1** Define postgres, controller, worker1-4 and named volumes (config parses) — Status: COMPLETED
    - [ ] **CW-008.2** `docker compose up -d` starts all six containers — Status: NOT STARTED — Depends on: CW-007.1, CW-007.2
    - [ ] **CW-008.3** Controller starts only after PostgreSQL is healthy — Status: NOT STARTED — Depends on: CW-008.2

- [ ] **CW-009: Configure logging and error handling**
  - Status: IN PROGRESS
  - Priority: MEDIUM
  - Depends on: CW-003
  - Description: Consistent logging and JSON error responses on both services.
  - Acceptance criteria: Handlers are exercised by tests; log output appears in containers at the configured level.
  - Verification: Unit tests; `docker compose logs`.
  - Notes: Verified 2026-10-20 via TestClient: controller `/metadata/cluster` and worker `/internal/chunks` return 501. The lifespan startup paths were not run in any check.
  - Subtasks:
    - [x] **CW-009.1** Unimplemented features return JSON 501 on both services — Status: COMPLETED
    - [ ] **CW-009.2** Map `CloudWeaveError` subclasses to HTTP status codes — Status: IN PROGRESS — Next: add a test per exception type
    - [ ] **CW-009.3** Controller logging configured at startup (`LOG_LEVEL`) — Status: IN PROGRESS — Next: run the controller with a database and check output
    - [ ] **CW-009.4** Worker logging configured at startup (`LOG_LEVEL`) — Status: IN PROGRESS — Next: run the worker locally and check output

- [x] **CW-010: Write the initial README**
  - Status: COMPLETED
  - Priority: MEDIUM
  - Depends on: CW-003
  - Description: Architecture, folder responsibilities, prerequisites and startup commands.
  - Acceptance criteria: README documents these topics.
  - Verification: Read `README.md`.
  - Notes: The startup commands in the README have not been executed (see CW-071.2).
  - Subtasks:
    - [x] **CW-010.1** README covers architecture, folders, prerequisites, startup commands — Status: COMPLETED

- [x] **CW-011: Validate imports and configuration**
  - Status: COMPLETED
  - Priority: HIGH
  - Depends on: CW-003, CW-004
  - Description: Detect obvious inconsistencies in imports and configuration.
  - Acceptance criteria: Imports, byte-compile and Compose parsing succeed.
  - Verification: Commands listed in Notes.
  - Notes: 2026-10-20: controller, worker, shared and client imported without error; `python -m compileall -q controller worker shared client` exited 0; `docker compose config` exited 0.
  - Subtasks:
    - [x] **CW-011.1** Import controller, worker, shared and client packages — Status: COMPLETED
    - [x] **CW-011.2** `python -m compileall` on all packages — Status: COMPLETED
    - [x] **CW-011.3** `docker compose config` parses — Status: COMPLETED

### Phase 1: Worker Storage

- [ ] **CW-012: Worker application core**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: A runnable worker with health, identity and internal-token protection.
  - Acceptance criteria: Worker starts, answers `/health` and `/info`, rejects unauthenticated internal calls.
  - Verification: TestClient plus a real `uvicorn` run.
  - Notes: 2026-10-20 TestClient checks: `/health` ok; `/info` returned `{'worker_id': 'workerZ', ...}` with `WORKER_ID=workerZ`; `/internal/chunks` gave 401 without the token and reached the handler (501) with it. A real `uvicorn` run has not been done.
  - Subtasks:
    - [x] **CW-012.1** App factory, settings, `GET /health`, `GET /info` — Status: COMPLETED
    - [x] **CW-012.2** Internal chunk routes require `X-Internal-Token` (401 otherwise) — Status: COMPLETED
    - [ ] **CW-012.3** Storage directory is created at startup — Status: IN PROGRESS — Next: run `uvicorn` with `STORAGE_DIR=./data` and check the directory

- [ ] **CW-013: Store binary chunks**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-003, CW-012
  - Description: Persist binary chunks as files under the worker storage root.
  - Acceptance criteria: A stored chunk can later be read back with identical bytes.
  - Verification: Worker storage unit tests and PUT API tests.
  - Notes: `ChunkStore` and `PUT /internal/chunks/{chunk_id}` exist as skeletons only.
  - Subtasks:
    - [ ] **CW-013.1** `ChunkStore.path_for` rejects IDs that could escape the storage root — Status: NOT STARTED
    - [ ] **CW-013.2** `ChunkStore.write` is atomic (temp file, fsync, rename) — Status: NOT STARTED — Depends on: CW-013.1
    - [ ] **CW-013.3** `PUT /internal/chunks/{chunk_id}` stores the raw body and returns 204 — Status: NOT STARTED — Depends on: CW-013.2
    - [ ] **CW-013.4** Repeating a PUT for the same chunk is safe — Status: NOT STARTED — Depends on: CW-013.3
    - [ ] **CW-013.5** Reject writes beyond configured capacity (507) — Status: NOT STARTED — Depends on: CW-013.3

- [ ] **CW-014: Retrieve chunks**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-013
  - Description: Retrieve a chunk by its unique ID.
  - Acceptance criteria: Existing chunks return exact bytes; missing chunks return an appropriate error (404).
  - Verification: Test successful retrieval and missing-chunk behaviour.
  - Notes: —
  - Subtasks:
    - [ ] **CW-014.1** `ChunkStore.read` returns bytes or raises `ChunkNotFoundError` — Status: NOT STARTED
    - [ ] **CW-014.2** `GET /internal/chunks/{chunk_id}` returns `application/octet-stream`, 404 if missing — Status: NOT STARTED — Depends on: CW-014.1

- [ ] **CW-015: Delete chunks**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-013
  - Description: Delete a chunk by ID.
  - Acceptance criteria: Deleted chunks are gone; deleting twice does not fail.
  - Verification: API tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-015.1** `ChunkStore.delete` is idempotent and reports whether the file existed — Status: NOT STARTED
    - [ ] **CW-015.2** `DELETE /internal/chunks/{chunk_id}` returns 204 and later GET returns 404 — Status: NOT STARTED — Depends on: CW-015.1

- [x] **CW-016: Unique worker IDs and configuration**
  - Status: COMPLETED
  - Priority: HIGH
  - Depends on: CW-008.1
  - Description: Four workers from one image, each with its own ID and advertised URL.
  - Acceptance criteria: `worker1` to `worker4` have distinct IDs, URLs and volumes.
  - Verification: Rendered Compose config and `/info`.
  - Notes: Verified in the rendered Compose config and via `/info` (2026-10-20). Running containers have not been checked.
  - Subtasks:
    - [x] **CW-016.1** `worker1`-`worker4` have distinct `WORKER_ID` and `ADVERTISE_URL` — Status: COMPLETED
    - [x] **CW-016.2** Worker reports its configured ID via `/info` — Status: COMPLETED

- [ ] **CW-017: Configure persistent worker storage**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-008, CW-013
  - Description: Each worker stores chunks on its own persistent volume.
  - Acceptance criteria: Chunks survive container stop/start and recreation.
  - Verification: Store a chunk, restart and recreate the container, read the chunk.
  - Notes: Volumes are declared in Compose; persistence has never been tested.
  - Subtasks:
    - [x] **CW-017.1** Each worker mounts its own named volume at `/data/chunks` — Status: COMPLETED
    - [ ] **CW-017.2** Chunks survive `docker stop/start` and container recreation — Status: NOT STARTED — Depends on: CW-013.3, CW-008.2

- [ ] **CW-018: Register workers**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-003, CW-004
  - Description: A worker announces itself to the controller on startup.
  - Acceptance criteria: Worker registers, retrying until the controller is reachable.
  - Verification: Unit tests with a mocked controller; Docker run.
  - Notes: `HeartbeatReporter` exists as a skeleton only.
  - Subtasks:
    - [ ] **CW-018.1** Build `WorkerRegistration` (ID, URL, usage, chunk inventory) — Status: NOT STARTED
    - [ ] **CW-018.2** POST registration with retry and backoff — Status: NOT STARTED — Depends on: CW-018.1
    - [ ] **CW-018.3** Re-register when the controller does not recognise the worker — Status: NOT STARTED — Depends on: CW-018.2

- [ ] **CW-019: Implement heartbeats**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-018
  - Description: Periodic heartbeats with usage statistics.
  - Acceptance criteria: Heartbeats are sent at the configured interval and survive controller outages.
  - Verification: Unit tests; container logs.
  - Notes: —
  - Subtasks:
    - [ ] **CW-019.1** Build `WorkerHeartbeat` (used bytes, chunk count, timestamp) — Status: NOT STARTED
    - [ ] **CW-019.2** Background loop every `HEARTBEAT_INTERVAL_SECONDS` — Status: NOT STARTED — Depends on: CW-019.1
    - [ ] **CW-019.3** A controller outage does not crash the worker — Status: NOT STARTED — Depends on: CW-019.2
    - [ ] **CW-019.4** Reporter starts in the lifespan and stops on shutdown — Status: NOT STARTED — Depends on: CW-019.2

- [ ] **CW-020: Report worker chunk inventories**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-013
  - Description: List stored chunks with sizes and checksums for registration and reconciliation.
  - Acceptance criteria: Inventory matches the files on disk.
  - Verification: Unit and API tests.
  - Notes: The worker has a skeleton `GET /internal/chunks`; the spec names `GET /internal/workers/{worker_id}/chunks` (see Section 6, decision D-4).
  - Subtasks:
    - [ ] **CW-020.1** `ChunkStore.list_chunks` returns ID, size, checksum — Status: NOT STARTED
    - [ ] **CW-020.2** `ChunkStore.used_bytes` reports usage — Status: NOT STARTED
    - [ ] **CW-020.3** Inventory endpoint exposed (host and path per D-4) — Status: NOT STARTED — Depends on: CW-020.1

- [ ] **CW-021: Worker unit tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-012
  - Description: Automated tests for the worker.
  - Acceptance criteria: Worker test suite passes.
  - Verification: `pytest worker/tests` (see CW-073.1 for how suites are run).
  - Notes: `worker/tests/` is empty.
  - Subtasks:
    - [ ] **CW-021.1** Test harness (pytest config, temp storage fixture, app client) — Status: NOT STARTED
    - [ ] **CW-021.2** `ChunkStore` tests (write, read, delete, inventory, path safety) — Status: NOT STARTED — Depends on: CW-021.1, CW-013.2, CW-014.1, CW-015.1, CW-020.1
    - [ ] **CW-021.3** Chunk API tests (auth, put, get, delete) — Status: NOT STARTED — Depends on: CW-021.1, CW-013.3, CW-014.2, CW-015.2
    - [ ] **CW-021.4** `HeartbeatReporter` tests with a mocked controller — Status: NOT STARTED — Depends on: CW-021.1, CW-019.2

### Phase 2: Database and Metadata

- [ ] **CW-022: Configure PostgreSQL**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-008
  - Description: PostgreSQL service for controller metadata.
  - Acceptance criteria: PostgreSQL starts healthy and the controller connects with `DATABASE_URL`.
  - Verification: `docker compose ps`; controller logs.
  - Notes: The `postgres` service (healthcheck, `postgres_data` volume) is defined and parse-checked only. It has never been started.
  - Subtasks:
    - [ ] **CW-022.1** `postgres` service with healthcheck and persistent volume reaches healthy — Status: IN PROGRESS — Next: `docker compose up -d postgres`
    - [ ] **CW-022.2** Controller connects using `DATABASE_URL` from the environment — Status: NOT STARTED — Depends on: CW-008.2

- [ ] **CW-023: Database connection and session management**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Engine, sessions and a request-scoped dependency.
  - Acceptance criteria: Sessions work against PostgreSQL and are always closed.
  - Verification: Integration test against PostgreSQL.
  - Notes: `engine`, `SessionLocal`, `get_db`, `init_db` are written but have never run against PostgreSQL.
  - Subtasks:
    - [ ] **CW-023.1** Engine, `SessionLocal` and `get_db` work against PostgreSQL — Status: IN PROGRESS — Next: verify after CW-022.2
    - [ ] **CW-023.2** Startup tolerates PostgreSQL not yet being ready (retry) — Status: NOT STARTED — Depends on: CW-022.2
    - [ ] **CW-023.3** Define commit and rollback boundaries in services and repositories — Status: NOT STARTED

- [ ] **CW-024: Object metadata model**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Table for objects: ID, name, size, content type, checksum, chunk count, timestamps.
  - Acceptance criteria: The schema can represent every required object attribute on PostgreSQL.
  - Verification: Create tables on PostgreSQL and inspect them.
  - Notes: `objects` has id, name, content_type, size_bytes, checksum, chunk_count, status, created_at. Mappers configured and tables created on in-memory SQLite on 2026-10-20 (not PostgreSQL). There is no last-modified column yet.
  - Subtasks:
    - [ ] **CW-024.1** Core columns created on PostgreSQL — Status: IN PROGRESS — Depends on: CW-022.2 — Next: verify on PostgreSQL
    - [ ] **CW-024.2** Add last-modified timestamp (`updated_at`) required by the spec — Status: NOT STARTED
    - [ ] **CW-024.3** Decide uniqueness and indexes for object names and document the decision — Status: NOT STARTED

- [ ] **CW-025: Chunk metadata model**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Table for chunks with ordering and checksums.
  - Acceptance criteria: Chunk order and integrity data are representable; deleting an object removes its chunks.
  - Verification: Database tests.
  - Notes: `chunks` (FK to objects, `chunk_index`, size, checksum, unique on object and index) exists; SQLite-only check.
  - Subtasks:
    - [ ] **CW-025.1** `chunks` table created on PostgreSQL — Status: IN PROGRESS — Depends on: CW-022.2 — Next: verify on PostgreSQL
    - [ ] **CW-025.2** Cascade delete from object to chunks and replicas works — Status: NOT STARTED — Depends on: CW-025.1

- [ ] **CW-026: Replica location model**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Table mapping chunks to workers with replica status.
  - Acceptance criteria: Replica locations and states are recorded.
  - Verification: Database tests.
  - Notes: `chunk_replicas` (composite key, status, `verified_at`) exists; SQLite-only check.
  - Subtasks:
    - [ ] **CW-026.1** `chunk_replicas` table created on PostgreSQL — Status: IN PROGRESS — Depends on: CW-022.2 — Next: verify on PostgreSQL
    - [ ] **CW-026.2** Define the replica status lifecycle and what happens when a worker is removed — Status: NOT STARTED

- [ ] **CW-027: Worker registry model**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Table of workers with status and last heartbeat.
  - Acceptance criteria: Worker state is persisted.
  - Verification: Database tests.
  - Notes: `workers` (id, base_url, status, capacity, used bytes, last_heartbeat) exists; SQLite-only check.
  - Subtasks:
    - [ ] **CW-027.1** `workers` table created on PostgreSQL — Status: IN PROGRESS — Depends on: CW-022.2 — Next: verify on PostgreSQL
    - [ ] **CW-027.2** Define status transitions (active, unhealthy, offline) and heartbeat updates — Status: NOT STARTED

- [ ] **CW-028: Support custom key-value metadata**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-024
  - Description: User-defined metadata per object.
  - Acceptance criteria: Arbitrary string key-value pairs can be stored, updated and returned.
  - Verification: Database and API tests.
  - Notes: Not present in the current schema. See decision D-3.
  - Subtasks:
    - [ ] **CW-028.1** Choose and implement storage (JSONB column or separate table) — Status: NOT STARTED
    - [ ] **CW-028.2** Validate keys and values (types, length limits) — Status: NOT STARTED — Depends on: CW-028.1
    - [ ] **CW-028.3** Pydantic schemas expose custom metadata — Status: NOT STARTED — Depends on: CW-028.1

- [ ] **CW-029: Database initialization and migrations**
  - Status: IN PROGRESS
  - Priority: MEDIUM
  - Depends on: CW-023
  - Description: Reliable, reproducible schema creation.
  - Acceptance criteria: Schema is created on a fresh database.
  - Verification: Start against an empty PostgreSQL.
  - Notes: `init_db` calls `create_all` at startup; verified only on SQLite. No migration tool.
  - Subtasks:
    - [ ] **CW-029.1** `init_db` creates tables on a fresh PostgreSQL — Status: IN PROGRESS — Depends on: CW-022.2 — Next: run against PostgreSQL
    - [ ] **CW-029.2** Adopt Alembic migrations, or record the decision to keep `create_all` — Status: NOT STARTED

- [ ] **CW-030: Implement database repositories**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-023, CW-024, CW-025, CW-026, CW-027
  - Description: All database access lives in repositories.
  - Acceptance criteria: Repositories implement their interfaces; no queries outside `repositories/`.
  - Verification: Repository tests and a search for queries elsewhere.
  - Notes: Repository classes exist as skeletons.
  - Subtasks:
    - [ ] **CW-030.1** `ObjectRepository` (create, get, list, update status, delete) — Status: NOT STARTED
    - [ ] **CW-030.2** `ChunkRepository` (chunks, replicas, under-replicated query) — Status: NOT STARTED
    - [ ] **CW-030.3** `WorkerRepository` (upsert, heartbeat, status) — Status: NOT STARTED
    - [ ] **CW-030.4** No SQLAlchemy queries in `api/` or `services/` — Status: NOT STARTED

- [ ] **CW-031: Database tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-030
  - Description: Tests for models and repositories on PostgreSQL.
  - Acceptance criteria: Database tests pass.
  - Verification: `pytest controller/tests`.
  - Notes: `controller/tests/` is empty.
  - Subtasks:
    - [ ] **CW-031.1** Fixture using real PostgreSQL with a clean schema per test — Status: NOT STARTED
    - [ ] **CW-031.2** Repository tests — Status: NOT STARTED — Depends on: CW-031.1
    - [ ] **CW-031.3** Constraint and cascade tests — Status: NOT STARTED — Depends on: CW-031.1

### Phase 3: Chunking and Object Storage

- [ ] **CW-032: Generate object and chunk IDs**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Unique IDs for objects and chunks.
  - Acceptance criteria: IDs are unique, URL-safe and filesystem-safe.
  - Verification: Unit tests.
  - Notes: See decision D-2 for the chunk ID scheme.
  - Subtasks:
    - [ ] **CW-032.1** Server-generated unique object IDs — Status: NOT STARTED
    - [ ] **CW-032.2** Chunk ID scheme that is unique, filesystem-safe and orderable — Status: NOT STARTED

- [ ] **CW-033: Split objects into 1 MB chunks**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-032
  - Description: Stream binary data into 1 MB chunks and handle edge cases.
  - Acceptance criteria: Correct chunks for all sizes; order preserved.
  - Verification: Unit tests with sizes 0, 1, 1 MB minus 1, 1 MB, 1 MB plus 1 and several MB.
  - Notes: `split_into_chunks` in `chunk_service.py` is written but has no tests. See decision D-1 for empty files.
  - Subtasks:
    - [ ] **CW-033.1** `split_into_chunks` streams 1 MB blocks — Status: IN PROGRESS — Next: write unit tests
    - [ ] **CW-033.2** Files smaller than 1 MB produce exactly one chunk — Status: NOT STARTED — Depends on: CW-033.1
    - [ ] **CW-033.3** Empty files handled per the documented policy — Status: NOT STARTED — Depends on: CW-033.1
    - [ ] **CW-033.4** Final partial chunk handled — Status: NOT STARTED — Depends on: CW-033.1
    - [ ] **CW-033.5** Exact multiples of 1 MB produce no zero-length trailing chunk — Status: NOT STARTED — Depends on: CW-033.1
    - [ ] **CW-033.6** Chunk indices are contiguous from 0 and order is preserved — Status: NOT STARTED — Depends on: CW-033.1

- [ ] **CW-034: Compute checksums**
  - Status: IN PROGRESS
  - Priority: HIGH
  - Depends on: CW-003
  - Description: SHA-256 checksums for chunks and whole objects.
  - Acceptance criteria: Checksums are computed at upload and persisted.
  - Verification: Unit tests against `hashlib`.
  - Notes: `sha256_hex` helpers exist in both controller and worker and are untested. The duplicate should be consolidated.
  - Subtasks:
    - [ ] **CW-034.1** SHA-256 helpers work and are tested — Status: IN PROGRESS — Next: write unit tests
    - [ ] **CW-034.2** Per-chunk checksum computed at upload and stored — Status: NOT STARTED — Depends on: CW-034.1
    - [ ] **CW-034.3** Whole-object streaming checksum — Status: NOT STARTED — Depends on: CW-034.1
    - [ ] **CW-034.4** One shared checksum implementation (remove the duplicate) — Status: NOT STARTED

- [ ] **CW-035: Store chunks on workers**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-013, CW-032
  - Description: The controller sends chunks to workers over internal HTTP.
  - Acceptance criteria: Chunks are stored on selected workers and acknowledged.
  - Verification: Integration test with workers.
  - Notes: `WorkerClient` is a skeleton.
  - Subtasks:
    - [ ] **CW-035.1** `WorkerClient.put_chunk` — Status: NOT STARTED
    - [ ] **CW-035.2** Write each chunk to every selected worker — Status: NOT STARTED — Depends on: CW-035.1
    - [ ] **CW-035.3** Confirm stored size and checksum from the worker — Status: NOT STARTED — Depends on: CW-035.1

- [ ] **CW-036: Commit metadata safely**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-024, CW-030, CW-035
  - Description: Record metadata only after storage outcomes are handled.
  - Acceptance criteria: An object is `available` only if its chunks were stored; failures leave no orphans.
  - Verification: Failure-injection tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-036.1** Create the object in an `uploading` state before chunk writes — Status: NOT STARTED
    - [ ] **CW-036.2** Mark `available` only after all chunk outcomes are handled — Status: NOT STARTED — Depends on: CW-036.1
    - [ ] **CW-036.3** Clean up orphan chunks and metadata after a failed upload — Status: NOT STARTED — Depends on: CW-036.1

- [ ] **CW-037: Reconstruct objects in order**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-035, CW-014
  - Description: Reassemble objects from ordered chunks.
  - Acceptance criteria: Downloaded bytes are identical to the original.
  - Verification: Round-trip tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-037.1** `WorkerClient.get_chunk` — Status: NOT STARTED
    - [ ] **CW-037.2** `ChunkService.read_chunk` selects a replica — Status: NOT STARTED — Depends on: CW-037.1
    - [ ] **CW-037.3** `ObjectService.download` streams chunks in index order — Status: NOT STARTED — Depends on: CW-037.2
    - [ ] **CW-037.4** Reassembled object checksum equals the stored checksum — Status: NOT STARTED — Depends on: CW-037.3

- [ ] **CW-038: Binary round-trip validation**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-037
  - Description: Round-trip tests for varied sizes and file types.
  - Acceptance criteria: Every round trip is byte-identical.
  - Verification: `pytest tests/integration`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-038.1** Sizes: 0, 1 byte, 1 MB minus 1, 1 MB, 1 MB plus 1, several MB — Status: NOT STARTED
    - [ ] **CW-038.2** Types: image, document, video, audio, archive — Status: NOT STARTED
    - [ ] **CW-038.3** Automated byte-for-byte (SHA-256) comparison helper — Status: NOT STARTED

### Phase 4: Distribution and Replication

- [ ] **CW-039: Discover healthy workers**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-018, CW-027
  - Description: The controller knows which workers are healthy.
  - Acceptance criteria: Only healthy workers are returned for placement.
  - Verification: Unit and integration tests.
  - Notes: `WorkerRegistry` is a skeleton.
  - Subtasks:
    - [ ] **CW-039.1** `WorkerRegistry.get_healthy_workers` excludes unhealthy and offline workers — Status: NOT STARTED
    - [ ] **CW-039.2** `NoHealthyWorkersError` when fewer workers than the replication factor are healthy — Status: NOT STARTED — Depends on: CW-039.1

- [ ] **CW-040: Select storage locations**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-039
  - Description: Choose workers for each chunk's replicas.
  - Acceptance criteria: Replicas of a chunk land on distinct workers and load is spread.
  - Verification: Unit tests.
  - Notes: `LeastLoadedPlacement` is a skeleton.
  - Subtasks:
    - [ ] **CW-040.1** `LeastLoadedPlacement.select_workers` returns the requested number of workers — Status: NOT STARTED
    - [ ] **CW-040.2** Never two replicas of one chunk on the same worker — Status: NOT STARTED — Depends on: CW-040.1
    - [ ] **CW-040.3** Chunks are distributed across all available workers — Status: NOT STARTED — Depends on: CW-040.1
    - [ ] **CW-040.4** Placement unit tests — Status: NOT STARTED — Depends on: CW-040.1

- [ ] **CW-041: Store two copies of each chunk and record locations**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-040, CW-035
  - Description: Every chunk gets two replicas on different workers, recorded in metadata.
  - Acceptance criteria: Metadata lists two distinct workers per chunk and both really hold the bytes.
  - Verification: Integration test comparing metadata with worker inventories.
  - Notes: See decision D-6 for what to do if only one replica can be written.
  - Subtasks:
    - [ ] **CW-041.1** Write each chunk to `REPLICATION_FACTOR` workers — Status: NOT STARTED
    - [ ] **CW-041.2** Record a replica row after each successful write — Status: NOT STARTED — Depends on: CW-041.1
    - [ ] **CW-041.3** Define the upload outcome when one replica cannot be written — Status: NOT STARTED

- [ ] **CW-042: Handle partial failures**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-041
  - Description: Failed writes retry or roll back without corrupting state.
  - Acceptance criteria: Failures end in a clean, defined state.
  - Verification: Failure-injection tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-042.1** Retry transient write failures with backoff — Status: NOT STARTED
    - [ ] **CW-042.2** Fall back to another worker when one fails — Status: NOT STARTED
    - [ ] **CW-042.3** Roll back when the policy cannot be satisfied — Status: NOT STARTED
    - [ ] **CW-042.4** Retries rely on an idempotent chunk PUT — Status: NOT STARTED — Depends on: CW-013.4

- [ ] **CW-043: Detect under-replicated chunks**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-041
  - Description: Find chunks with fewer healthy replicas than the replication factor.
  - Acceptance criteria: All such chunks are found, none wrongly reported.
  - Verification: Tests with simulated worker loss.
  - Notes: —
  - Subtasks:
    - [ ] **CW-043.1** `ChunkRepository.find_under_replicated` — Status: NOT STARTED
    - [ ] **CW-043.2** `ReplicationManager.find_under_replicated` counts healthy replicas only — Status: NOT STARTED — Depends on: CW-043.1

- [ ] **CW-044: Restore missing replicas**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-043
  - Description: Copy chunks to healthy workers to restore the replication factor.
  - Acceptance criteria: Replication returns to 2 where capacity exists.
  - Verification: Integration test.
  - Notes: —
  - Subtasks:
    - [ ] **CW-044.1** `ReplicationManager.replicate_chunk` copies from a healthy replica to a new worker — Status: NOT STARTED
    - [ ] **CW-044.2** `restore_replication` handles every under-replicated chunk — Status: NOT STARTED — Depends on: CW-044.1
    - [ ] **CW-044.3** Restoration runs in the background when worker status changes — Status: NOT STARTED — Depends on: CW-044.2
    - [ ] **CW-044.4** Concurrent repairs of the same chunk are prevented — Status: NOT STARTED — Depends on: CW-044.2

- [ ] **CW-045: Verify distribution and replica placement**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-040, CW-041
  - Description: Make chunk locations visible and testable.
  - Acceptance criteria: Distribution across workers is demonstrable.
  - Verification: Test run and visible output.
  - Notes: —
  - Subtasks:
    - [ ] **CW-045.1** Integration test with four workers checks distribution and replica count — Status: NOT STARTED
    - [ ] **CW-045.2** A way to list chunk locations for an object (endpoint output or helper) — Status: NOT STARTED

### Phase 5: Client REST APIs

- [ ] **CW-046: Align routes with the spec contract**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-003
  - Description: Current routes differ from the spec (see Section 6).
  - Acceptance criteria: Routes match the spec's paths and methods.
  - Verification: Compare the OpenAPI path list with the spec.
  - Notes: The scaffold registers `/objects` and `/metadata/objects/{id}`; the spec requires `/api/v1/objects...` and `GET`/`PATCH` on `/api/v1/objects/{object_id}/metadata`. There is no PATCH route.
  - Subtasks:
    - [ ] **CW-046.1** Serve client routes under `/api/v1` — Status: NOT STARTED
    - [ ] **CW-046.2** Metadata at `GET` and `PATCH /api/v1/objects/{object_id}/metadata` — Status: NOT STARTED — Depends on: CW-046.1
    - [ ] **CW-046.3** Internal routes per spec, including `GET /internal/workers/{worker_id}/chunks` — Status: NOT STARTED
    - [ ] **CW-046.4** Decide where cluster status lives (for example `/api/v1/cluster`) — Status: NOT STARTED

- [ ] **CW-047: Upload objects — `POST /api/v1/objects`**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-046, CW-036, CW-028
  - Description: Multipart upload with an optional custom-metadata JSON field.
  - Acceptance criteria: Returns 201 with object info; invalid input returns 400.
  - Verification: API tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-047.1** Accept `multipart/form-data` with required field `file` — Status: NOT STARTED
    - [ ] **CW-047.2** Optional JSON field `metadata`; invalid JSON returns 400 — Status: NOT STARTED — Depends on: CW-028.1
    - [ ] **CW-047.3** Return 201 with object ID, name, size, content type, checksum, chunk count — Status: NOT STARTED
    - [ ] **CW-047.4** Stream the upload without holding the whole file in memory — Status: NOT STARTED

- [ ] **CW-048: Download objects — `GET /api/v1/objects/{object_id}`**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-046, CW-037
  - Description: Return the original bytes with the right content type.
  - Acceptance criteria: 200 with an identical body; 404 if the object does not exist.
  - Verification: API tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-048.1** Stream the reassembled object — Status: NOT STARTED
    - [ ] **CW-048.2** `Content-Type` from upload; `Content-Disposition` with filename — Status: NOT STARTED
    - [ ] **CW-048.3** 404 JSON error for an unknown object — Status: NOT STARTED
    - [ ] **CW-048.4** 503 JSON error when no replica of a chunk is reachable — Status: NOT STARTED — Depends on: CW-056.3

- [ ] **CW-049: Retrieve metadata — `GET /api/v1/objects/{object_id}/metadata`**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-046, CW-028, CW-030
  - Description: Return metadata without downloading the data.
  - Acceptance criteria: System and custom metadata returned; 404 when unknown.
  - Verification: API tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-049.1** Response contains system fields, custom metadata and chunk information — Status: NOT STARTED
    - [ ] **CW-049.2** 404 JSON error for an unknown object — Status: NOT STARTED

- [ ] **CW-050: Update custom metadata — `PATCH /api/v1/objects/{object_id}/metadata`**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-046, CW-028
  - Description: Add or update custom metadata without re-uploading data.
  - Acceptance criteria: 200 with updated metadata and no chunk traffic; 404 if unknown.
  - Verification: API tests.
  - Notes: See decision D-3 for how keys are removed.
  - Subtasks:
    - [ ] **CW-050.1** Merge keys from the JSON body — Status: NOT STARTED
    - [ ] **CW-050.2** Update the last-modified time — Status: NOT STARTED — Depends on: CW-024.2
    - [ ] **CW-050.3** 400 for an invalid body and 404 for an unknown object — Status: NOT STARTED
    - [ ] **CW-050.4** No worker requests are made during a metadata update — Status: NOT STARTED

- [ ] **CW-051: Delete objects — `DELETE /api/v1/objects/{object_id}`**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-046, CW-035
  - Description: Delete an object and its stored chunks.
  - Acceptance criteria: 204 on success; 404 if unknown; worker inventories no longer list the chunks.
  - Verification: API and integration tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-051.1** Return 204 No Content — Status: NOT STARTED
    - [ ] **CW-051.2** Return 404 JSON error for an unknown object — Status: NOT STARTED
    - [ ] **CW-051.3** Remove replicas from workers, then remove metadata — Status: NOT STARTED
    - [ ] **CW-051.4** Handle unreachable workers (cleanup later through reconciliation) — Status: NOT STARTED — Depends on: CW-058.3

- [ ] **CW-052: List objects — `GET /api/v1/objects`**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-046, CW-030
  - Description: List stored objects.
  - Acceptance criteria: Each entry has ID, name, size and content type.
  - Verification: API tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-052.1** Return object ID, name, size, content type (and timestamps) — Status: NOT STARTED
    - [ ] **CW-052.2** Pagination with offset, limit and total count — Status: NOT STARTED

- [ ] **CW-053: HTTP status codes and error responses**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-009
  - Description: Meaningful JSON errors using the spec's status codes.
  - Acceptance criteria: 400, 404, 409, 500 and 503 behave as the spec describes.
  - Verification: API tests.
  - Notes: See decision D-5 for 409.
  - Subtasks:
    - [ ] **CW-053.1** Every error is JSON with a message (including validation errors) — Status: NOT STARTED
    - [ ] **CW-053.2** Map 400, 404, 500 and 503 conditions — Status: NOT STARTED
    - [ ] **CW-053.3** Decide and implement 409 usage — Status: NOT STARTED

### Phase 6: Worker Failure Recovery

- [ ] **CW-054: Controller-side registration and heartbeat endpoints**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-027, CW-030, CW-018
  - Description: The controller accepts worker registrations and heartbeats.
  - Acceptance criteria: Workers register and heartbeats update their state.
  - Verification: API tests; Docker logs.
  - Notes: Routes exist in `internal_workers.py`; `WorkerRegistry` is a skeleton.
  - Subtasks:
    - [ ] **CW-054.1** Register endpoint upserts the worker as active — Status: NOT STARTED
    - [ ] **CW-054.2** Heartbeat endpoint updates last-seen time and usage — Status: NOT STARTED
    - [ ] **CW-054.3** Heartbeat interval and timeout relationship documented and validated — Status: NOT STARTED
    - [ ] **CW-054.4** Heartbeat from an unknown worker prompts re-registration — Status: NOT STARTED

- [ ] **CW-055: Monitor heartbeats and detect unavailable workers**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-054
  - Description: Detect workers that stop heartbeating without reacting to brief hiccups.
  - Acceptance criteria: Silent workers become unavailable after the timeout; brief outages cause no copying.
  - Verification: Unit and Docker tests.
  - Notes: `HealthMonitor` is a skeleton.
  - Subtasks:
    - [ ] **CW-055.1** Persist last-seen timestamps — Status: NOT STARTED
    - [ ] **CW-055.2** `HealthMonitor` loop started in the controller lifespan — Status: NOT STARTED
    - [ ] **CW-055.3** Mark workers unavailable after `HEARTBEAT_TIMEOUT_SECONDS` — Status: NOT STARTED — Depends on: CW-055.2
    - [ ] **CW-055.4** Grace period before re-replication so temporary failures do not trigger copying — Status: NOT STARTED — Depends on: CW-055.3

- [ ] **CW-056: Serve reads from surviving replicas**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-037, CW-055
  - Description: Reads succeed while at least one replica of each chunk is reachable.
  - Acceptance criteria: Downloads succeed with one worker down.
  - Verification: Docker and unit tests.
  - Notes: —
  - Subtasks:
    - [ ] **CW-056.1** Locate healthy replicas of a chunk — Status: NOT STARTED
    - [ ] **CW-056.2** Try the next replica on connection or read failure — Status: NOT STARTED — Depends on: CW-056.1
    - [ ] **CW-056.3** Clear 503 when no replica is reachable — Status: NOT STARTED — Depends on: CW-056.1

- [ ] **CW-057: Detect lost replicas and restore replication**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-044, CW-055
  - Description: React to worker loss by restoring the replication factor.
  - Acceptance criteria: Replication returns to 2 wherever healthy capacity exists.
  - Verification: Docker test.
  - Notes: —
  - Subtasks:
    - [ ] **CW-057.1** A worker going offline triggers an under-replication check — Status: NOT STARTED
    - [ ] **CW-057.2** Restore replicas to healthy workers not already holding the chunk — Status: NOT STARTED — Depends on: CW-057.1
    - [ ] **CW-057.3** Defined behaviour when fewer healthy workers than the factor remain (stay degraded and report) — Status: NOT STARTED

- [ ] **CW-058: Restart workers and reconcile inventories**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-054, CW-020
  - Description: A restarted worker rejoins and is reconciled against metadata.
  - Acceptance criteria: The worker is active again and inventories are consistent.
  - Verification: Docker test.
  - Notes: —
  - Subtasks:
    - [ ] **CW-058.1** A restarted worker re-registers and becomes active — Status: NOT STARTED
    - [ ] **CW-058.2** Compare worker-reported chunks with metadata — Status: NOT STARTED
    - [ ] **CW-058.3** Remove or adopt orphan chunks found during reconciliation — Status: NOT STARTED — Depends on: CW-058.2
    - [ ] **CW-058.4** Handle over-replication after a worker rejoins — Status: NOT STARTED — Depends on: CW-058.2

- [ ] **CW-059: Docker-based worker failure tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-057, CW-058
  - Description: Automated tests that stop and start worker containers.
  - Acceptance criteria: Tests assert system behaviour during and after a failure.
  - Verification: `pytest tests/failure_recovery`.
  - Notes: `tests/failure_recovery/` is empty.
  - Subtasks:
    - [ ] **CW-059.1** `docker stop worker2` is detected — Status: NOT STARTED
    - [ ] **CW-059.2** `docker start worker2` re-registers — Status: NOT STARTED
    - [ ] **CW-059.3** Shared helpers for stopping and starting containers — Status: NOT STARTED

- [ ] **CW-060: Required worker-failure scenario**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-059
  - Description: Make the spec's failure demonstration repeatable.
  - Acceptance criteria: All six steps run with real, recorded results.
  - Verification: Run the scenario and keep the output.
  - Notes: —
  - Subtasks:
    - [ ] **CW-060.1** Upload an object with two replicas per chunk — Status: NOT STARTED
    - [ ] **CW-060.2** Stop `worker2` — Status: NOT STARTED
    - [ ] **CW-060.3** Verify retrieval succeeds from surviving replicas — Status: NOT STARTED
    - [ ] **CW-060.4** Verify the system detects the lost replication — Status: NOT STARTED
    - [ ] **CW-060.5** Restart `worker2` — Status: NOT STARTED
    - [ ] **CW-060.6** Verify re-registration and replication reconciliation — Status: NOT STARTED

### Phase 7: Data Integrity

- [ ] **CW-061: Checksum generation**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-034
  - Description: Generate and store SHA-256 checksums at upload/write time.
  - Acceptance criteria: Checksum values exist in metadata and on workers for all written chunks.
  - Verification: Database query and worker response inspection.
  - Notes: —
  - Subtasks:
    - [ ] **CW-061.1** Chunk SHA-256 stored in metadata at upload — Status: NOT STARTED — Depends on: CW-034.2
    - [ ] **CW-061.2** Worker computes and returns checksum on write acknowledgement — Status: NOT STARTED — Depends on: CW-013.3

- [ ] **CW-062: Checksum verification during reads**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-037, CW-061
  - Description: Re-calculate and verify checksum before returning data to the client.
  - Acceptance criteria: Any chunk whose checksum does not match expected value is flagged and rejected.
  - Verification: Unit test with mismatched data.
  - Notes: —
  - Subtasks:
    - [ ] **CW-062.1** Verify chunk checksum on every read — Status: NOT STARTED
    - [ ] **CW-062.2** Buffer/verify chunk before streaming so bad bytes are never emitted to client — Status: NOT STARTED — Depends on: CW-062.1

- [ ] **CW-063: Corruption detection**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-061, CW-013
  - Description: Endpoint and service logic to actively detect corrupted or missing chunks on workers.
  - Acceptance criteria: Corrupted chunks or missing files are correctly identified.
  - Verification: Worker verify test.
  - Notes: Worker has skeleton `POST /internal/chunks/{chunk_id}/verify`.
  - Subtasks:
    - [ ] **CW-063.1** `POST /internal/chunks/{chunk_id}/verify` re-hashes chunk file on worker — Status: NOT STARTED
    - [ ] **CW-063.2** `IntegrityRepairer.verify_chunk` queries workers and records corruption status in DB — Status: NOT STARTED — Depends on: CW-063.1
    - [ ] **CW-063.3** Missing chunk files on worker detected as missing replicas — Status: NOT STARTED — Depends on: CW-063.1

- [ ] **CW-064: Alternative replica fallback**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-062, CW-063, CW-056
  - Description: When a corrupted replica is encountered, automatically failover to a valid replica.
  - Acceptance criteria: Corrupt bytes are never returned when a valid copy is available.
  - Verification: Inject bad bytes into one replica, download object, assert download matches original.
  - Notes: —
  - Subtasks:
    - [ ] **CW-064.1** Read fallback triggers on checksum mismatch — Status: NOT STARTED
    - [ ] **CW-064.2** End-to-end assert that corrupt bytes never leak into response stream — Status: NOT STARTED — Depends on: CW-064.1

- [ ] **CW-065: Repair corrupted replicas**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-064, CW-044
  - Description: Overwrite corrupted replica on the worker using bytes from a good replica.
  - Acceptance criteria: Corrupted replica is restored and subsequent verification passes.
  - Verification: Corrupt replica -> trigger repair -> verify chunk returns clean.
  - Notes: —
  - Subtasks:
    - [ ] **CW-065.1** `IntegrityRepairer.repair_chunk` re-fetches valid replica and overwrites corrupted worker — Status: NOT STARTED
    - [ ] **CW-065.2** Periodic background scrub (`scan_all`) to detect and repair corruption at rest — Status: NOT STARTED — Depends on: CW-065.1

- [ ] **CW-066: All replicas corrupted or unavailable**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-064
  - Description: Handle unrecoverable data loss gracefully.
  - Acceptance criteria: Clean 500/503 JSON error; object status marked degraded/corrupt in metadata.
  - Verification: Corrupt both replicas of a chunk and test download.
  - Notes: —
  - Subtasks:
    - [ ] **CW-066.1** Return descriptive error response when no valid replica exists — Status: NOT STARTED
    - [ ] **CW-066.2** Mark object status as degraded in database — Status: NOT STARTED

- [ ] **CW-067: Controlled corruption demonstration**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-065
  - Description: Scripted demonstration of intentional chunk corruption and recovery.
  - Acceptance criteria: Demonstrate corruption injection, failover during read, and replica repair.
  - Verification: Execute demo script and capture output.
  - Notes: —
  - Subtasks:
    - [ ] **CW-067.1** Script to modify/corrupt bytes in a worker volume file — Status: NOT STARTED
    - [ ] **CW-067.2** Read object while corrupt and verify correct data returned — Status: NOT STARTED — Depends on: CW-067.1
    - [ ] **CW-067.3** Trigger repair and verify both replicas healthy again — Status: NOT STARTED — Depends on: CW-067.1

### Phase 8: Client and Documentation

- [ ] **CW-068: Python HTTP client**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-046
  - Description: Reusable Python client library in `client/client.py`.
  - Acceptance criteria: Full coverage of all client-facing REST APIs with appropriate error handling.
  - Verification: Automated client tests against running controller.
  - Notes: Skeleton exists with `NotImplementedError`.
  - Subtasks:
    - [ ] **CW-068.1** Implement `upload` method (streaming multipart + metadata) — Status: NOT STARTED
    - [ ] **CW-068.2** Implement `download` method (streaming to local file) — Status: NOT STARTED
    - [ ] **CW-068.3** Implement `list_objects`, `metadata`, `delete`, `cluster_status` — Status: NOT STARTED
    - [ ] **CW-068.4** Map HTTP error status codes to custom client exceptions — Status: NOT STARTED

- [ ] **CW-069: Command-line interface (CLI)**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-068
  - Description: Interactive CLI commands in `client/cli.py`.
  - Acceptance criteria: All subcommands (`upload`, `download`, `list`, `metadata`, `delete`, `cluster`) work.
  - Verification: Execute CLI commands against running cluster.
  - Notes: Argument parser is scaffolded; commands delegate to client.
  - Subtasks:
    - [ ] **CW-069.1** Wire up `upload` and `download` CLI actions — Status: NOT STARTED
    - [ ] **CW-069.2** Wire up `list`, `metadata` (view and update), `delete`, `cluster` — Status: NOT STARTED
    - [ ] **CW-069.3** Human-readable error and progress output — Status: NOT STARTED

- [ ] **CW-070: API documentation**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-046
  - Description: Comprehensive API documentation and OpenAPI schemas.
  - Acceptance criteria: Interactive Swagger UI at `/docs` is descriptive and accurate; Markdown docs in `docs/`.
  - Verification: Manual inspection of `/docs`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-070.1** Document all request/response models with descriptions in FastAPI — Status: NOT STARTED
    - [ ] **CW-070.2** Write `docs/api.md` with curl examples and request/response samples — Status: NOT STARTED

- [ ] **CW-071: Deployment and setup documentation**
  - Status: NOT STARTED
  - Priority: MEDIUM
  - Depends on: CW-008
  - Description: Step-by-step setup, configuration, and operational guide in README.
  - Acceptance criteria: A user can clone the repo and run the system following the guide.
  - Verification: Test clean start on an independent machine/clean directory.
  - Notes: Basic README exists; needs update with validated instructions once stack is runnable.
  - Subtasks:
    - [ ] **CW-071.1** Document all environment variables in a reference table — Status: NOT STARTED
    - [ ] **CW-071.2** Verify and record exact startup and shutdown commands in README — Status: NOT STARTED
    - [ ] **CW-071.3** Document Windows-specific tips (PowerShell vs Make) — Status: NOT STARTED

- [ ] **CW-072: Troubleshooting documentation**
  - Status: NOT STARTED
  - Priority: LOW
  - Depends on: CW-071
  - Description: Guide for debugging common issues (Postgres connection, worker offline, volume permissions).
  - Acceptance criteria: `docs/troubleshooting.md` exists with actionable solutions.
  - Verification: Manual review.
  - Notes: —
  - Subtasks:
    - [ ] **CW-072.1** Create `docs/troubleshooting.md` covering common failure modes — Status: NOT STARTED

### Phase 9: Testing

- [ ] **CW-073: Test infrastructure and harnesses**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-003, CW-005
  - Description: Test harness setup allowing independent test runs for controller, worker, and cross-service suites.
  - Acceptance criteria: `pytest` runs cleanly without module import conflicts between controller and worker.
  - Verification: Run `pytest` on an empty or dummy test.
  - Notes: Both services use top-level `app`, requiring separate pytest invocations or specific pythonpath configuration.
  - Subtasks:
    - [ ] **CW-073.1** Configure separate pytest discovery/commands for controller and worker — Status: NOT STARTED
    - [ ] **CW-073.2** Create shared fixtures (temporary directories, sample binary files) — Status: NOT STARTED

- [ ] **CW-074: Unit tests for core modules**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-073, CW-033, CW-034, CW-040
  - Description: Isolated unit tests for chunking, checksumming, and placement logic.
  - Acceptance criteria: 100% pass rate for pure logic unit tests.
  - Verification: `pytest controller/tests worker/tests`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-074.1** Unit tests for `split_into_chunks` and boundary conditions — Status: NOT STARTED
    - [ ] **CW-074.2** Unit tests for SHA-256 calculation and stream hashing — Status: NOT STARTED
    - [ ] **CW-074.3** Unit tests for `LeastLoadedPlacement` algorithm — Status: NOT STARTED

- [ ] **CW-075: Controller REST API integration tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-047, CW-048, CW-049, CW-050, CW-051, CW-052
  - Description: Test all client API endpoints using FastAPI TestClient with a test database.
  - Acceptance criteria: All endpoints return expected status codes and payloads.
  - Verification: Automated API test run.
  - Notes: —
  - Subtasks:
    - [ ] **CW-075.1** Test `POST /api/v1/objects` with valid and invalid inputs — Status: NOT STARTED
    - [ ] **CW-075.2** Test `GET /api/v1/objects/{object_id}` download — Status: NOT STARTED
    - [ ] **CW-075.3** Test metadata retrieval and PATCH updates without re-upload — Status: NOT STARTED
    - [ ] **CW-075.4** Test object deletion and 404s for missing objects — Status: NOT STARTED
    - [ ] **CW-075.5** Test object listing with pagination — Status: NOT STARTED

- [ ] **CW-076: Chunking, distribution, and ordering tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-038, CW-045
  - Description: End-to-end test verifying multi-MB files split into chunks, placed across workers, and reassembled in exact order.
  - Acceptance criteria: Reassembled file has identical SHA-256 digest to source file.
  - Verification: Integration test with 4 workers.
  - Notes: —
  - Subtasks:
    - [ ] **CW-076.1** Upload 5 MB binary object and verify chunk creation across workers — Status: NOT STARTED
    - [ ] **CW-076.2** Verify chunk indices and ordering preserved during reassembly — Status: NOT STARTED
    - [ ] **CW-076.3** Verify exactly 2 replicas per chunk on distinct workers — Status: NOT STARTED

- [ ] **CW-077: Replication and under-replication tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-043, CW-044
  - Description: Verify detection of under-replicated chunks and recovery.
  - Acceptance criteria: Loss of a replica triggers re-replication back to factor 2.
  - Verification: Automated test simulating worker drop.
  - Notes: —
  - Subtasks:
    - [ ] **CW-077.1** Query under-replicated chunks when a worker goes down — Status: NOT STARTED
    - [ ] **CW-077.2** Test replication restoration copying chunk to remaining healthy worker — Status: NOT STARTED

- [ ] **CW-078: Worker failure and recovery tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-059
  - Description: Automated tests stopping and restarting Docker worker containers.
  - Acceptance criteria: System remains operational during single worker downtime.
  - Verification: `pytest tests/failure_recovery`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-078.1** Read availability test while 1 worker container is stopped — Status: NOT STARTED
    - [ ] **CW-078.2** Re-registration and inventory reconciliation on container restart — Status: NOT STARTED

- [ ] **CW-079: Data integrity and corruption tests**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-065
  - Description: Automated tests injecting bad bytes into chunk files.
  - Acceptance criteria: Corrupted replica detected; good replica served; bad replica repaired.
  - Verification: `pytest tests/data_integrity`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-079.1** Corrupt single replica; verify download succeeds and repair executes — Status: NOT STARTED
    - [ ] **CW-079.2** Corrupt all replicas; verify clean error response (no corrupted stream emitted) — Status: NOT STARTED

- [ ] **CW-080: End-to-end acceptance validation**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-075, CW-076, CW-077, CW-078, CW-079
  - Description: Complete suite run validating every spec requirement.
  - Acceptance criteria: All test suites pass against a running Docker Compose cluster.
  - Verification: `make test` or full pytest execution.
  - Notes: —
  - Subtasks:
    - [ ] **CW-080.1** Document test matrix and map to assignment requirements — Status: NOT STARTED
    - [ ] **CW-080.2** Execute full suite against Docker Compose cluster and save log — Status: NOT STARTED

### Phase 10: Final Demonstration

- [ ] **CW-081: Clean startup verification**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-008, CW-071
  - Description: Start entire cluster from clean state using documented commands.
  - Acceptance criteria: Controller, PostgreSQL, and 4 workers reach healthy state.
  - Verification: `docker compose up -d` -> all containers running and healthy.
  - Notes: —
  - Subtasks:
    - [ ] **CW-081.1** Execute startup commands from scratch — Status: NOT STARTED
    - [ ] **CW-081.2** Verify 4 workers registered with controller via cluster status API — Status: NOT STARTED

- [ ] **CW-082: Demo 1 — Basic object storage and round-trip**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-081, CW-047, CW-048
  - Description: Upload arbitrary binary object (image/pdf/video) and retrieve it.
  - Acceptance criteria: SHA-256 hash of downloaded object equals original object.
  - Verification: Compare original and downloaded file checksums.
  - Notes: —
  - Subtasks:
    - [ ] **CW-082.1** Upload binary file and record object ID and hash — Status: NOT STARTED
    - [ ] **CW-082.2** Download object and verify identical checksum — Status: NOT STARTED

- [ ] **CW-083: Demo 2 — Chunking and worker distribution**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-082
  - Description: Upload file > 1 MB (e.g. 3.5 MB) and demonstrate chunk division.
  - Acceptance criteria: File is split into multiple 1 MB chunks (and 1 partial chunk) distributed across workers.
  - Verification: Inspect chunk metadata via API and worker volumes.
  - Notes: —
  - Subtasks:
    - [ ] **CW-083.1** Upload 3.5 MB file (producing 4 chunks: 1MB, 1MB, 1MB, 0.5MB) — Status: NOT STARTED
    - [ ] **CW-083.2** Display chunk layout and demonstrate chunks spread across workers — Status: NOT STARTED

- [ ] **CW-084: Demo 3 — Replication factor of 2**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-083
  - Description: Show that each chunk is stored on exactly two distinct workers.
  - Acceptance criteria: Metadata shows 2 replicas per chunk on different worker nodes.
  - Verification: Query object metadata endpoint.
  - Notes: —
  - Subtasks:
    - [ ] **CW-084.1** Inspect replica mapping for each chunk of an object — Status: NOT STARTED
    - [ ] **CW-084.2** Confirm that no two replicas of the same chunk reside on the same worker — Status: NOT STARTED

- [ ] **CW-085: Demo 4 — Custom metadata management**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-082, CW-050
  - Description: Upload custom metadata, retrieve it, and update it without re-uploading the file.
  - Acceptance criteria: Custom metadata updated; object data unchanged; no chunk data transferred.
  - Verification: API calls with timestamps and network/payload inspection.
  - Notes: —
  - Subtasks:
    - [ ] **CW-085.1** Upload object with custom metadata `{"author": "alice", "project": "cloud"}` — Status: NOT STARTED
    - [ ] **CW-085.2** Retrieve metadata and confirm custom fields — Status: NOT STARTED
    - [ ] **CW-085.3** PATCH metadata with `{"project": "cloudweave", "version": "1.0"}` and verify update — Status: NOT STARTED

- [ ] **CW-086: Demo 5 — Worker failure and recovery**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-084, CW-060
  - Description: Demonstrate `docker stop worker2` and subsequent `docker start worker2`.
  - Acceptance criteria: Object remains readable while worker2 is stopped; replication restored; worker2 rejoins cleanly.
  - Verification: Step-by-step terminal execution with recorded output.
  - Notes: —
  - Subtasks:
    - [ ] **CW-086.1** Stop worker2 container (`docker stop worker2`) — Status: NOT STARTED
    - [ ] **CW-086.2** Download object successfully from surviving replicas — Status: NOT STARTED
    - [ ] **CW-086.3** Show controller detecting under-replicated chunks — Status: NOT STARTED
    - [ ] **CW-086.4** Restart worker2 (`docker start worker2`) and show re-registration — Status: NOT STARTED

- [ ] **CW-087: Demo 6 — Intentional corruption and repair**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-084, CW-067
  - Description: Intentionally corrupt a chunk file on disk and demonstrate detection and repair.
  - Acceptance criteria: Corrupted replica detected; valid replica used for download; corrupt replica repaired.
  - Verification: Binary modification of chunk file on disk + API download + repair verification.
  - Notes: —
  - Subtasks:
    - [ ] **CW-087.1** Overwrite bytes of a chunk on worker1's storage volume — Status: NOT STARTED
    - [ ] **CW-087.2** Initiate download and show successful download from worker2's replica — Status: NOT STARTED
    - [ ] **CW-087.3** Run repair and confirm worker1's replica is restored and valid — Status: NOT STARTED

- [ ] **CW-088: Documentation and demonstration evidence collection**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-082, CW-083, CW-084, CW-085, CW-086, CW-087
  - Description: Collect command outputs, logs, and screenshots/transcripts into `docs/demo-evidence.md`.
  - Acceptance criteria: Complete, reproducible evidence for all 6 required demonstrations.
  - Verification: Review `docs/demo-evidence.md`.
  - Notes: —
  - Subtasks:
    - [ ] **CW-088.1** Create `docs/demo-evidence.md` with recorded command outputs for Demos 1-6 — Status: NOT STARTED
    - [ ] **CW-088.2** Update main `README.md` to link to evidence document — Status: NOT STARTED

- [ ] **CW-089: Final project acceptance review**
  - Status: NOT STARTED
  - Priority: HIGH
  - Depends on: CW-088, CW-080
  - Description: Comprehensive review against the assignment specification.
  - Acceptance criteria: Every functional and non-functional requirement satisfied.
  - Verification: Check off final acceptance checklist.
  - Notes: —
  - Subtasks:
    - [ ] **CW-089.1** Audit against assignment specification requirements — Status: NOT STARTED
    - [ ] **CW-089.2** Final code cleanup, removal of unused debug artifacts, verify `.gitignore` — Status: NOT STARTED

---

## 5. Testing and Demonstration Checklist

Quick cross-reference mapping the assignment spec demonstrations to task IDs.

| Demonstration | Description | Primary Task | Supporting Tasks | Status |
|---|---|---|---|---|
| **Demo 1** | Object storage & retrieval round-trip (byte-for-byte equality) | **CW-082** | CW-038, CW-047, CW-048 | NOT STARTED |
| **Demo 2** | Chunking across workers for files > 1 MB | **CW-083** | CW-033, CW-045, CW-076 | NOT STARTED |
| **Demo 3** | Replication factor 2 across distinct workers | **CW-084** | CW-041, CW-045, CW-076 | NOT STARTED |
| **Demo 4** | Custom metadata upload, read, and PATCH without re-upload | **CW-085** | CW-028, CW-049, CW-050 | NOT STARTED |
| **Demo 5** | Worker failure handling (`docker stop worker2` / `start worker2`) | **CW-086** | CW-056, CW-057, CW-060 | NOT STARTED |
| **Demo 6** | Controlled data corruption detection and replica repair | **CW-087** | CW-063, CW-064, CW-067 | NOT STARTED |

---

## 6. Blockers, Open Decisions, and Notes

### Current Blockers
- **None**: No tasks are currently marked `BLOCKED`.

### Open Design Decisions

| ID | Decision | Recommendation | Related Tasks |
|---|---|---|---|
| **D-1** | Empty (0-byte) file handling | Store with `size_bytes = 0`, `chunk_count = 0`, no worker chunks, SHA-256 of empty string `e3b0c44...`. | CW-033.3, CW-047 |
| **D-2** | Chunk ID format | `<object_id>_<chunk_index>` (e.g. `obj123_0`, `obj123_1`). Clean, predictable, filesystem-safe. | CW-032.2, CW-013.1 |
| **D-3** | Custom metadata schema & deletion | Store as PostgreSQL `JSONB` on `objects` table. In `PATCH`, provide `null` to delete a key, or provide new string value to add/update. | CW-028.1, CW-050.1 |
| **D-4** | Endpoint for listing worker chunks | Worker exposes `GET /internal/chunks` (inventory). Controller exposes `GET /internal/workers/{worker_id}/chunks` by querying metadata or proxying. | CW-020.3, CW-046.3 |
| **D-5** | Usage of HTTP 409 Conflict | Return 409 when attempting an operation on an object currently being deleted or uploaded. | CW-053.3 |
| **D-6** | Upload behavior on single-replica failure | Require both replicas to succeed during initial upload; if one fails and retries/fallbacks fail, abort and roll back upload with 503. | CW-041.3, CW-042.3 |

### Known Implementation & Environment Gaps (as of 2026-10-20)
1. **API route prefix mismatch**: Current controller scaffold registers `/objects` instead of `/api/v1/objects` required by spec (tracked in **CW-046**).
2. **Missing PATCH endpoint**: Current controller has no `PATCH /api/v1/objects/{object_id}/metadata` router (tracked in **CW-046**, **CW-050**).
3. **Database unverified**: Models have only been compiled and tested against in-memory SQLite; PostgreSQL container has not been launched (tracked in **CW-022**, **CW-023**).
4. **Docker images not built**: `controller/Dockerfile` and `worker/Dockerfile` written but not built or tested (tracked in **CW-007**).
5. **No automated tests written**: `tests/`, `controller/tests/`, `worker/tests/` contain only `.gitkeep` (tracked in Phase 9).
6. **No tracking script**: Maintained manually per user instructions.

---

## 7. Next Tasks to Work On

Recommended immediate next tasks in order of logical progression:

1. **CW-007: Build Dockerfiles** (`CW-007.1`, `CW-007.2`) — Verify that controller and worker Docker images build successfully with `shared/` context.
2. **CW-008: Start Docker Compose stack** (`CW-008.2`) — Verify that PostgreSQL, controller, and 4 workers start up and reach healthy states.
3. **CW-022 / CW-023: Verify PostgreSQL connectivity** (`CW-022.1`, `CW-023.1`) — Connect controller to Postgres container and verify table creation on real PostgreSQL.
4. **CW-013: Implement worker chunk storage** (`CW-013.1` to `CW-013.3`) — Implement file writing, directory safety, and PUT endpoint on storage workers.
5. **CW-014: Implement worker chunk retrieval** (`CW-014.1`, `CW-014.2`) — Implement GET endpoint on storage workers to read raw bytes.
6. **CW-046: Align controller REST API routes** (`CW-046.1`, `CW-046.2`) — Prefix client routes with `/api/v1` and add `PATCH /metadata` route stub.

