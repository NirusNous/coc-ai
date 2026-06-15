import type { FormEvent } from "react";
import { createWorkflow } from "../api/workflows";
import { useWorkflowStore } from "../store/workflowStore";

export function PromptBar() {
  const prompt = useWorkflowStore((state) => state.prompt);
  const status = useWorkflowStore((state) => state.status);
  const setPrompt = useWorkflowStore((state) => state.setPrompt);
  const beginSubmission = useWorkflowStore((state) => state.beginSubmission);
  const workflowStarted = useWorkflowStore((state) => state.workflowStarted);
  const failWorkflow = useWorkflowStore((state) => state.failWorkflow);
  const resetWorkflow = useWorkflowStore((state) => state.resetWorkflow);

  const isSubmitting = status === "submitting";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!prompt.trim()) {
      failWorkflow("Please enter a prompt first.");
      return;
    }

    beginSubmission();

    try {
      const response = await createWorkflow(prompt);
      workflowStarted(response);
    } catch (error) {
      failWorkflow(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <section className="promptPanel">
      <div>
        <p className="eyebrow">Agentic OS</p>
        <h1>Prompt-to-Preview Factory</h1>
        <p className="subtitle">
          Describe an app. The system will eventually generate files, run the
          app, and show a live preview.
        </p>
      </div>

      <form className="promptForm" onSubmit={handleSubmit}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Example: Build a task manager app with add, complete, and delete task functionality."
        />

        <div className="promptActions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Starting..." : "Start Workflow"}
          </button>

          <button type="button" className="secondaryButton" onClick={resetWorkflow}>
            Reset
          </button>
        </div>
      </form>
    </section>
  );
}