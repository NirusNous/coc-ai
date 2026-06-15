from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="Agentic OS API")


origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WorkflowRequest(BaseModel):
    prompt: str


@app.get("/")
async def root():
    return {
        "message": "Agentic OS API is running"
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "agentic-os-api"
    }


@app.post("/api/workflows")
async def create_workflow(request: WorkflowRequest):
    workflow_id = f"workflow_{uuid4().hex[:8]}"

    return {
        "workflowId": workflow_id,
        "status": "started",
        "prompt": request.prompt
    }