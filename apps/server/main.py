from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import WorkflowRequest, WorkflowResponse
from app.workflows.workflow_engine import WorkflowEngine


app = FastAPI(title="Agentic OS API")
workflow_engine = WorkflowEngine()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "agentic-os-api",
    }


@app.post("/api/workflows", response_model=WorkflowResponse)
async def create_workflow(request: WorkflowRequest):
    return await workflow_engine.run(request.prompt)
