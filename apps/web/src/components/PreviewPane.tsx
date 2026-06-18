import {
  cleanWorkflowWorkspace,
  restartWorkflowPreview,
  stopWorkflowPreview
} from "../api/workflows";
import { useWorkflowStore } from "../store/workflowStore";

export function PreviewPane() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const previewUrl = useWorkflowStore((state) => state.previewUrl);
  const workspacePath = useWorkflowStore((state) => state.workspacePath);
  const status = useWorkflowStore((state) => state.status);
  const previewAction = useWorkflowStore((state) => state.previewAction);
  const beginPreviewAction = useWorkflowStore(
    (state) => state.beginPreviewAction
  );
  const failPreviewAction = useWorkflowStore(
    (state) => state.failPreviewAction
  );

  const controlsDisabled = previewAction !== null;
  const canStop = Boolean(workflowId && previewUrl) && !controlsDisabled;
  const canRestart = Boolean(workflowId && workspacePath) && !controlsDisabled;
  const canClean = Boolean(workflowId && workspacePath) && !controlsDisabled;

  async function handleStopPreview() {
    if (!workflowId) {
      return;
    }

    beginPreviewAction("stopping", "Requesting preview stop...");

    try {
      await stopWorkflowPreview(workflowId);
    } catch (error) {
      failPreviewAction(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleRestartPreview() {
    if (!workflowId) {
      return;
    }

    beginPreviewAction("restarting", "Requesting preview restart...");

    try {
      await restartWorkflowPreview(workflowId);
    } catch (error) {
      failPreviewAction(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleCleanWorkspace() {
    if (!workflowId) {
      return;
    }

    beginPreviewAction("cleaning", "Requesting workspace cleanup...");

    try {
      await cleanWorkflowWorkspace(workflowId);
    } catch (error) {
      failPreviewAction(error instanceof Error ? error.message : String(error));
    }
  }

  let placeholderTitle = "No preview yet";
  let placeholderBody =
    "The active preview runner will render the generated app here.";

  if (status === "awaiting_approval") {
    placeholderTitle = "Awaiting architecture approval";
    placeholderBody =
      "The workflow is paused before code generation. Review the plan summary and approve it or request changes.";
  } else if (status === "preview_restarting") {
    placeholderTitle = "Restarting preview";
    placeholderBody = "The generated app is restarting from the existing workspace.";
  } else if (status === "install_failed") {
    placeholderTitle = "Dependency install failed";
    placeholderBody = "Check the logs for package manager output from the install stage.";
  } else if (status === "build_failed") {
    placeholderTitle = "Build failed";
    placeholderBody =
      "The generated app did not compile successfully. Review the logs for build output.";
  } else if (status === "preview_failed") {
    placeholderTitle = "Preview startup failed";
    placeholderBody = "The app built, but the preview server did not become ready.";
  } else if (status === "timeout") {
    placeholderTitle = "Runner timed out";
    placeholderBody = "One of the runner stages exceeded its timeout. Check the latest logs.";
  } else if (status === "runtime_crashed") {
    placeholderTitle = "Runtime crashed";
    placeholderBody = "The preview process exited before the app became ready.";
  } else if (status === "failed") {
    placeholderTitle = "Workflow failed";
    placeholderBody =
      "The workflow ended before the preview became ready. Check the latest logs and attempt history.";
  } else if (status === "preview_stopped") {
    placeholderTitle = "Preview stopped";
    placeholderBody = "Use Restart Preview to bring the generated app back.";
  } else if (status === "workspace_cleaned") {
    placeholderTitle = "Workspace cleaned";
    placeholderBody = "Start a new workflow to generate a fresh preview workspace.";
  }

  return (
    <section className="panel previewPane">
      <div className="panelHeader">
        <h2>Live Preview</h2>
        <div className="panelActions">
          <button
            type="button"
            className="secondaryButton"
            disabled={!canStop}
            onClick={handleStopPreview}
          >
            {previewAction === "stopping" ? "Stopping..." : "Stop Preview"}
          </button>

          <button
            type="button"
            className="secondaryButton"
            disabled={!canRestart}
            onClick={handleRestartPreview}
          >
            {previewAction === "restarting" ? "Restarting..." : "Restart Preview"}
          </button>

          <button
            type="button"
            className="dangerButton"
            disabled={!canClean}
            onClick={handleCleanWorkspace}
          >
            {previewAction === "cleaning" ? "Cleaning..." : "Clean Workspace"}
          </button>
        </div>
      </div>

      {previewUrl ? (
        <iframe title="Generated app preview" src={previewUrl} />
      ) : (
        <div className="previewPlaceholder">
          <div>
            <strong>{placeholderTitle}</strong>
            <p>{placeholderBody}</p>
          </div>
        </div>
      )}
    </section>
  );
}
