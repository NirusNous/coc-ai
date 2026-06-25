# COC AI

COC AI is a desktop-style PWA for generating frontend application workspaces from natural language prompts. The app turns a prompt into requirements, architecture, generated files, a runnable preview, and a persisted workflow history.

## Current stack

- Frontend: React + TypeScript + Vite + Zustand
- Backend: FastAPI + WebSockets + SQLite
- Preview runner: Local runner
- LLM integration:
  - Requirements Agent
  - Architecture Agent
  - Code Generation Agent
  - Debug Agent
  - Patch Agent

## What the app does

1. Submit a prompt.
2. Generate requirements and architecture.
3. Pause for architecture approval.
4. Generate frontend files.
5. Write the generated workspace to `generated/<workflow_id>/`.
6. Run install, build, and preview validation through the local preview runner.
7. If validation fails, run Debug Agent and Patch Agent retries before giving up.
8. Persist workflow history, logs, files, and preview metadata in SQLite.

## Run

### Backend

```powershell
cd apps/server
python -m uvicorn main:app --reload
```

### Frontend

```powershell
cd apps/web
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Environment

Backend configuration lives in `apps/server/.env`.

```powershell
LLM_API_KEY="optional-for-local-openai-compatible-servers"
LLM_MODEL="qwen2.5-coder:7b"
LLM_BASE_URL="http://127.0.0.1:11434/v1"
MAX_LLM_CONCURRENCY="1"
MAX_OUTPUT_TOKENS="800"
LLM_TIMEOUT_SECONDS="120"
```

## Preview runner

The local runner:

- installs dependencies
- runs `pnpm run build`
- starts the preview app
- exposes preview control through the API

## Main API surface

### Workflows

- `POST /api/workflows`
- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `POST /api/workflows/{workflow_id}/approve`
- `POST /api/workflows/{workflow_id}/request-changes`

### Preview control

- `GET /api/previews`
- `POST /api/workflows/{workflow_id}/preview/restart`
- `DELETE /api/workflows/{workflow_id}/preview`
- `DELETE /api/workflows/{workflow_id}/workspace`

## Persistence

SQLite data is stored at:

- `data/agentic_os.sqlite3`

Persisted workflow data includes:

- prompt
- status
- requirements
- architecture
- generated files
- logs
- attempts
- preview URL
- workspace path

## Test

### Frontend

```powershell
cd apps/web
npm run build
```

### Backend

```powershell
cd apps/server
python -m py_compile main.py app\\agents.py app\\workflow.py app\\config.py
```

Recommended manual checks:

1. Start a workflow.
2. Confirm requirements and architecture appear.
3. Approve the architecture.
4. Confirm files are generated and written to disk.
5. Confirm the Build/Test Agent moves through install and build status.
6. If validation fails, confirm the Debug Agent and Patch Agent run and the attempt counter advances.
7. Confirm preview starts only after validation succeeds.
8. Force an install or build failure and confirm the workflow retries and eventually settles on success or a final failure state.
9. Stop and restart the preview.
10. Clean the workspace.
11. Reload the page and confirm workflow history restores correctly.

## Notes

- Generated workspaces stay out of Git.
- No Docker or Kubernetes runner is used in this phase.
- The app currently generates frontend-only applications.
