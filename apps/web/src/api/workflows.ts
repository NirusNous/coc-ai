import type { WorkflowResponse } from "../types/workflow";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function createWorkflow(
  prompt: string
): Promise<WorkflowResponse> {
  const response = await fetch(`${API_BASE_URL}/api/workflows`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      prompt
    })
  });

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

  return response.json() as Promise<WorkflowResponse>;
}