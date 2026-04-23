# Task: Production-Grade Dynamic Publishing Pipeline

## Phase 1: Database Layer
- [x] Add `ApiCredentialPool` model to `database.py`

## Phase 2: Credential Pool Infrastructure
- [x] Create `backend/agent/publishing/__init__.py`
- [x] Create `backend/agent/publishing/credential_pool.py`
- [x] Create `backend/agent/publishing/handlers/__init__.py`

## Phase 3: Platform API Handlers
- [x] Create `handlers/buffer.py`
- [x] (Scrapped Facebook Graph in favor of ALL Buffer cascade)

## Phase 4: Rewire Publisher & Scheduler
- [x] Fix `backend/agent/nodes/publisher.py` (remove duplicate, convert to API-first)
- [x] Update `backend/scheduler.py` (`_execute_job` uses credential pool)

## Phase 5: Pool Management API & UI
- [x] Create `backend/api/publishing_pool.py`
- [x] Register router in `backend/main.py`
- [x] Update Settings Page UI (Publishing Fleet tab)
