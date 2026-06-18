import { useWorkflowStore } from "../store/workflowStore";

export function AttemptHistory() {
  const attempts = useWorkflowStore((state) => state.attempts);
  const currentAttempt = useWorkflowStore((state) => state.currentAttempt);
  const maxAttempts = useWorkflowStore((state) => state.maxAttempts);
  const isRetrying = useWorkflowStore((state) => state.isRetrying);

  return (
    <section className="panel attemptHistory">
      <div className="panelHeader">
        <h2>Attempt History</h2>
      </div>

      <div className="attemptSummary">
        <strong>
          Attempt {currentAttempt}/{maxAttempts}
        </strong>
        <span>{isRetrying ? "retrying" : "stable"}</span>
      </div>

      {attempts.length === 0 ? (
        <div className="emptyState">
          Runner validation attempts will appear here after the generated app is
          written to disk.
        </div>
      ) : (
        <div className="attemptList">
          {attempts.map((attempt) => (
            <article key={attempt.attemptNumber} className="attemptItem">
              <div className="attemptHeader">
                <strong>Attempt {attempt.attemptNumber}</strong>
                <span>{attempt.status}</span>
              </div>

              <p>{attempt.summary}</p>

              {attempt.debugSummary ? (
                <small>{attempt.debugSummary}</small>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
