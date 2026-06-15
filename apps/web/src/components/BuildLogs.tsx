import { useWorkflowStore } from "../store/workflowStore";

export function BuildLogs() {
  const logs = useWorkflowStore((state) => state.logs);

  return (
    <section className="panel buildLogs">
      <div className="panelHeader">
        <h2>Logs</h2>
      </div>

      <pre>{logs.join("\n")}</pre>
    </section>
  );
}