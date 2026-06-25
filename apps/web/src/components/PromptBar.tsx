import { useRef } from "react";
import type { FormEvent } from "react";
import { createWorkflow } from "../api/workflows";
import { connectWorkflowSocket } from "../api/workflowSocket";
import { useWorkflowStore } from "../store/workflowStore";

export function PromptBar() {
  const socketCleanupRef = useRef<null | (() => void)>(null);

  const prompt = useWorkflowStore((state) => state.prompt);
  const status = useWorkflowStore((state) => state.status);
  const setPrompt = useWorkflowStore((state) => state.setPrompt);
  const beginSubmission = useWorkflowStore((state) => state.beginSubmission);
  const workflowQueued = useWorkflowStore((state) => state.workflowQueued);
  const handleWorkflowEvent = useWorkflowStore(
    (state) => state.handleWorkflowEvent
  );
  const failWorkflow = useWorkflowStore((state) => state.failWorkflow);
  const resetWorkflow = useWorkflowStore((state) => state.resetWorkflow);

  const isSubmitting =
    status === "submitting" ||
    status === "queued" ||
    status === "running" ||
    status === "awaiting_approval";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!prompt.trim()) {
      failWorkflow("Please enter a prompt first.");
      return;
    }

    beginSubmission();

    try {
      const response = await createWorkflow(prompt);

      workflowQueued(response);

      socketCleanupRef.current?.();

      socketCleanupRef.current = connectWorkflowSocket(
        response.workflowId,
        handleWorkflowEvent,
        failWorkflow
      );
    } catch (error) {
      failWorkflow(error instanceof Error ? error.message : String(error));
    }
  }

  function handleReset() {
    socketCleanupRef.current?.();
    socketCleanupRef.current = null;
    resetWorkflow();
  }

  return (
    <section className="promptPanel">
      <div>
        <p className="eyebrow">Agentic OS</p>
        <h1>App Generation Workspace</h1>
        <p className="subtitle">
          Describe the product you want to build. The system will plan it,
          generate the client app, and stream progress as the preview comes up.
        </p>
      </div>

      <form className="promptForm" onSubmit={handleSubmit}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Example: Build a customer feedback dashboard with filters, record detail editing, and local persistence."
        />

        <div className="promptActions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Running..." : "Start Workflow"}
          </button>

          <button
            type="button"
            className="secondaryButton"
            onClick={handleReset}
          >
            Reset
          </button>
        </div>
      </form>
    </section>
  );
}
