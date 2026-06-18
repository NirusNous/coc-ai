import type { WorkflowSocketEvent } from "../types/workflow";

const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL ?? "ws://127.0.0.1:8000";

export function connectWorkflowSocket(
  workflowId: string,
  onEvent: (event: WorkflowSocketEvent) => void,
  onError: (message: string) => void
) {
  const socket = new WebSocket(
    `${WS_BASE_URL}/ws/workflows/${workflowId}`
  );

  socket.onmessage = (messageEvent) => {
    try {
      const event = JSON.parse(messageEvent.data) as WorkflowSocketEvent;
      onEvent(event);
    } catch {
      onError("Received invalid workflow event from server.");
    }
  };

  socket.onerror = () => {
    onError("Workflow WebSocket connection error.");
  };

  socket.onclose = () => {
    // Normal for now. Later we can show disconnected state.
  };

  return () => {
    if (
      socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING
    ) {
      socket.close();
    }
  };
}