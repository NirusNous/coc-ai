from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import WorkflowRequest, WorkflowResponse
from app.workflow import run_mock_workflow


app = FastAPI(title="Agentic OS API")


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
def health():
    return {
        "status": "ok",
        "service": "agentic-os-api",
    }


@app.post("/api/workflows", response_model=WorkflowResponse)
def create_workflow(request: WorkflowRequest):
    prompt = request.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")
    return run_mock_workflow(prompt)
