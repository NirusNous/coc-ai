import { useWorkflowStore } from "../store/workflowStore";

export function StatusBar() {
  const status = useWorkflowStore((state) => state.status);
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const workspacePath = useWorkflowStore((state) => state.workspacePath);
  const previewUrl = useWorkflowStore((state) => state.previewUrl);

  return (
    <section className="statusBar">
      <div>
        <span className="statusLabel">Status</span>
        <strong>{status}</strong>
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
    </section>
  );
}