import { useWorkflowStore } from "../store/workflowStore";

export function LogsPanel() {
  const logs = useWorkflowStore((state) => state.logs);

  return (
    <section className="panel logsPanel">
      <div className="panelHeader">
        <h2>Logs</h2>
      </div>

      <pre>{logs.join("\n")}</pre>
    </section>
  );
}
