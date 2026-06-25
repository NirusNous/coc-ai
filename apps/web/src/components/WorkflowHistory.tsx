import { useEffect, useState } from "react";
import {
  getWorkflow,
  listWorkflows
} from "../api/workflows";
import { useWorkflowStore } from "../store/workflowStore";
import type { WorkflowSummary } from "../types/workflow";

function formatTimestamp(timestamp: string) {
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }

  return date.toLocaleString();
}

export function WorkflowHistory() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const status = useWorkflowStore((state) => state.status);
  const previewAction = useWorkflowStore((state) => state.previewAction);
  const restoreWorkflow = useWorkflowStore((state) => state.restoreWorkflow);

  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingWorkflowId, setLoadingWorkflowId] = useState<string | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  const isBusy =
    status === "submitting" ||
    status === "queued" ||
    status === "running" ||
    status === "awaiting_approval" ||
    status === "code_generated" ||
    status === "files_written" ||
    status === "preview_restarting" ||
    previewAction !== null;

  useEffect(() => {
    let isCancelled = false;

    async function loadHistory() {
      setIsLoading(true);

      try {
        const response = await listWorkflows();

        if (!isCancelled) {
          setWorkflows(response.workflows);
          setError(null);
        }
      } catch (loadError) {
        if (!isCancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : String(loadError)
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadHistory();

    return () => {
      isCancelled = true;
    };
  }, [workflowId, status]);

  async function handleSelectWorkflow(selectedWorkflowId: string) {
    setLoadingWorkflowId(selectedWorkflowId);
    setError(null);

    try {
      const workflow = await getWorkflow(selectedWorkflowId);
      restoreWorkflow(workflow);
    } catch (selectError) {
      setError(
        selectError instanceof Error
          ? selectError.message
          : String(selectError)
      );
    } finally {
      setLoadingWorkflowId(null);
    }
  }

  return (
    <section className="panel workflowHistory">
      <div className="panelHeader">
        <h2>Workflow History</h2>
      </div>

      {isLoading ? (
        <div className="emptyState">Loading saved workflows...</div>
      ) : workflows.length === 0 ? (
        <div className="emptyState">
          Saved workflows will appear here after they are persisted by the
          backend.
        </div>
      ) : (
        <div className="historyList">
          {workflows.map((workflow) => (
            <button
              key={workflow.workflowId}
              type="button"
              className={`historyItem ${
                workflow.workflowId === workflowId ? "selected" : ""
              }`}
              disabled={isBusy || loadingWorkflowId === workflow.workflowId}
              onClick={() => handleSelectWorkflow(workflow.workflowId)}
            >
              <div className="historyHeader">
                <strong>{workflow.workflowId}</strong>
                <span>{workflow.status}</span>
              </div>

              <p>{workflow.prompt}</p>

              <div className="historyMeta">
                <small>{formatTimestamp(workflow.updatedAt)}</small>
                <small>
                  {workflow.previewUrl ? "preview saved" : "no preview"}
                </small>
              </div>
            </button>
          ))}
        </div>
      )}

      {error ? <p className="historyError">{error}</p> : null}
    </section>
  );
}
