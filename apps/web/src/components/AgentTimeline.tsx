import { useWorkflowStore } from "../store/workflowStore";

export function AgentTimeline() {
  const agentEvents = useWorkflowStore((state) => state.agentEvents);

  return (
    <section className="panel agentTimeline">
      <div className="panelHeader">
        <h2>Agent Status</h2>
      </div>

      <div className="timelineList">
        {agentEvents.map((event) => (
          <article key={event.id} className={`timelineItem ${event.status}`}>
            <div className="timelineDot" />

            <div>
              <h3>{event.name}</h3>
              <p>{event.detail}</p>
              <span>{event.status}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}