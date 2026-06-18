import type {
  ChangeRequestScope,
  ProjectListResponse,
  ProjectResponse,
  PreviewActionResponse,
  PreviewListResponse,
  WorkflowActionResponse,
  WorkflowHistoryResponse,
  WorkflowResponse,
  WorkflowStartResponse
} from "../types/workflow";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function requestJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const errorData = await response.json();
      message = errorData.detail ?? errorData.error ?? message;
    } catch {
      message = `Request failed with status ${response.status}`;
      console.error("Failed to parse error response:", message);
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export async function createWorkflow(
  prompt: string,
  projectId: string
): Promise<WorkflowStartResponse> {
  return requestJson<WorkflowStartResponse>("/api/workflows", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      prompt,
      projectId
    })
  });
}

export async function listWorkflows(): Promise<WorkflowHistoryResponse> {
  return requestJson<WorkflowHistoryResponse>("/api/workflows");
}

export async function listProjectWorkflows(
  projectId: string
): Promise<WorkflowHistoryResponse> {
  return requestJson<WorkflowHistoryResponse>(
    `/api/projects/${projectId}/workflows`
  );
}

export async function getWorkflow(
  workflowId: string
): Promise<WorkflowResponse> {
  return requestJson<WorkflowResponse>(`/api/workflows/${workflowId}`);
}

export async function listProjects(): Promise<ProjectListResponse> {
  return requestJson<ProjectListResponse>("/api/projects");
}

export async function createProject(
  name: string,
  description?: string
): Promise<ProjectResponse> {
  return requestJson<ProjectResponse>("/api/projects", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      name,
      description
    })
  });
}

export async function approveWorkflow(
  workflowId: string,
  note?: string
): Promise<WorkflowActionResponse> {
  return requestJson<WorkflowActionResponse>(
    `/api/workflows/${workflowId}/approve`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        note
      })
    }
  );
}

export async function requestWorkflowChanges(
  workflowId: string,
  scope: ChangeRequestScope,
  feedback: string
): Promise<WorkflowActionResponse> {
  return requestJson<WorkflowActionResponse>(
    `/api/workflows/${workflowId}/request-changes`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        scope,
        feedback
      })
    }
  );
}

export async function listPreviews(): Promise<PreviewListResponse> {
  return requestJson<PreviewListResponse>("/api/previews");
}

export async function restartWorkflowPreview(
  workflowId: string
): Promise<PreviewActionResponse> {
  return requestJson<PreviewActionResponse>(
    `/api/workflows/${workflowId}/preview/restart`,
    {
      method: "POST"
    }
  );
}

export async function stopWorkflowPreview(
  workflowId: string
): Promise<PreviewActionResponse> {
  return requestJson<PreviewActionResponse>(
    `/api/workflows/${workflowId}/preview`,
    {
      method: "DELETE"
    }
  );
}

export async function cleanWorkflowWorkspace(
  workflowId: string
): Promise<PreviewActionResponse> {
  return requestJson<PreviewActionResponse>(
    `/api/workflows/${workflowId}/workspace`,
    {
      method: "DELETE"
    }
  );
}
