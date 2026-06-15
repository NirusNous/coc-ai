import { useWorkflowStore } from "../store/workflowStore";

export function PlanSummary() {
  const requirements = useWorkflowStore((state) => state.requirements);
  const architecture = useWorkflowStore((state) => state.architecture);

  return (
    <section className="panel planSummary">
      <div className="panelHeader">
        <h2>Plan Summary</h2>
      </div>

      {!requirements || !architecture ? (
        <div className="emptyState">
          Requirements and architecture will appear here after workflow execution.
        </div>
      ) : (
        <div className="planContent">
          <div>
            <h3>{requirements.appName}</h3>
            <p>{requirements.summary}</p>
          </div>

          <div>
            <h3>Features</h3>
            <ul>
              {requirements.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
          </div>

          <div>
            <h3>Stack</h3>
            <p>
              {architecture.stack.frontend} + {architecture.stack.language} +{" "}
              {architecture.stack.buildTool}
            </p>
          </div>

          <div>
            <h3>Components</h3>
            <ul>
              {architecture.components.map((component) => (
                <li key={component.name}>
                  <strong>{component.name}</strong>: {component.responsibility}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}