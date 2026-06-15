import { useWorkflowStore } from "../store/workflowStore";

export function StatusBar() {
  const status = useWorkflowStore((state) => state.status);
  const workflowId = useWorkflowStore((state) => state.workflowId);

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
    </section>
  );
}