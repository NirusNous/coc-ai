# COC AI

COC AI is a desktop-style PWA for generating frontend application workspaces from natural language prompts. The app turns a prompt into requirements, architecture, generated files, a runnable preview, and a persisted workflow history.

## Current stack

- Frontend: React + TypeScript + Vite + Zustand
- Backend: FastAPI + WebSockets + SQLite
- Preview runners:
  - Local runner
  - Rancher-managed Kubernetes runner
- LLM integration:
  - Requirements Agent
  - Architecture Agent
  - Code Generation Agent

## What the app does

1. Create or select a project.
2. Submit a prompt.
3. Generate requirements and architecture.
4. Pause for architecture approval.
5. Generate frontend files.
6. Write the generated workspace to `generated/<project_id>/<workflow_id>/`.
7. Run install, build, and preview validation through the active preview runner.
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

AGENTIC_OS_RUNNER="local"
KUBECONFIG_PATH=""
K8S_CONTEXT=""
AGENTIC_OS_NAMESPACE_PREFIX="agentic-os"
PREVIEW_EXPOSURE_MODE="port_forward"
PREVIEW_BASE_DOMAIN=""
```

## Preview runners

### Local runner

The local runner:

- installs dependencies
- runs `pnpm run build`
- starts the preview app
- exposes preview control through the API

### Rancher/Kubernetes runner

The Kubernetes runner:

- uses `kubectl` with the configured kubeconfig and context
- creates one namespace per workflow
- mounts the generated workspace through a ConfigMap
- runs a Kubernetes Job for install and build validation
- streams Kubernetes Job logs through the existing workflow log channel
- marks the workflow as `install_failed`, `build_failed`, or `timeout` when cluster validation fails
- creates a preview Deployment and Service only after the build Job succeeds
- exposes the preview through either:
  - `kubectl port-forward`
  - Ingress

If `kubectl config current-context` is not set, Kubernetes endpoints fail cleanly and the local runner remains available.

## Main API surface

### Workflows

- `POST /api/workflows`
- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `POST /api/workflows/{workflow_id}/approve`
- `POST /api/workflows/{workflow_id}/request-changes`

### Projects

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `GET /api/projects/{project_id}/workflows`

### Preview control

- `GET /api/previews`
- `POST /api/workflows/{workflow_id}/preview/restart`
- `DELETE /api/workflows/{workflow_id}/preview`
- `DELETE /api/workflows/{workflow_id}/workspace`

### Runner and Kubernetes helpers

- `GET /api/runner`
- `GET /api/kubernetes/namespaces`
- `POST /api/kubernetes/test-namespace`
- `DELETE /api/kubernetes/namespaces/{namespace}`

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
- project association

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

1. Create a project.
2. Start a workflow.
3. Confirm requirements and architecture appear.
4. Approve the architecture.
5. Confirm files are generated and written to disk.
6. Confirm the Build/Test Agent moves through install and build status.
7. Confirm preview starts only after validation succeeds.
8. Force an install or build failure and confirm the workflow stops with `install_failed` or `build_failed`.
9. Stop and restart the preview.
10. Clean the workspace.
11. Reload the page and confirm workflow history restores correctly.
12. If using Kubernetes, confirm a valid `kubectl` context exists before testing the Kubernetes runner.

## Notes

- Generated workspaces stay out of Git.
- No Docker CLI is used.
- The app currently generates frontend-only applications.
