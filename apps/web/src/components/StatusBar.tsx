import { useWorkflowStore } from "../store/workflowStore";

export function StatusBar() {
  const status = useWorkflowStore((state) => state.status);
  const selectedProjectId = useWorkflowStore(
    (state) => state.selectedProjectId
  );
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const workspacePath = useWorkflowStore((state) => state.workspacePath);
  const previewUrl = useWorkflowStore((state) => state.previewUrl);
  const currentAttempt = useWorkflowStore((state) => state.currentAttempt);
  const maxAttempts = useWorkflowStore((state) => state.maxAttempts);
  const isRetrying = useWorkflowStore((state) => state.isRetrying);
  const approvalStage = useWorkflowStore((state) => state.approvalStage);

  return (
    <section className="statusBar">
      <div>
        <span className="statusLabel">Status</span>
        <strong>{status}</strong>
      </div>

      <div>
        <span className="statusLabel">Project</span>
        <strong>{selectedProjectId ?? "none"}</strong>
      </div>

      <div>
        <span className="statusLabel">Workflow</span>
        <strong>{workflowId ?? "none"}</strong>
      </div>

      <div>
        <span className="statusLabel">Workspace</span>
        <strong>{workspacePath ?? "not created"}</strong>
      </div>

      <div>
        <span className="statusLabel">Preview</span>
        <strong>{previewUrl ?? "not running"}</strong>
      </div>

      <div>
        <span className="statusLabel">Attempt</span>
        <strong>
          {currentAttempt}/{maxAttempts}
        </strong>
      </div>

      <div>
        <span className="statusLabel">Retrying</span>
        <strong>{isRetrying ? "yes" : "no"}</strong>
      </div>

      <div>
        <span className="statusLabel">Approval</span>
        <strong>{approvalStage ?? "none"}</strong>
      </div>
    </section>
  );
}
