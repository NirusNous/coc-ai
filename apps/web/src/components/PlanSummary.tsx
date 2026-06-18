import { useEffect, useState } from "react";
import {
  approveWorkflow,
  requestWorkflowChanges
} from "../api/workflows";
import { useWorkflowStore } from "../store/workflowStore";
import type { ChangeRequestScope } from "../types/workflow";

export function PlanSummary() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const status = useWorkflowStore((state) => state.status);
  const requirements = useWorkflowStore((state) => state.requirements);
  const architecture = useWorkflowStore((state) => state.architecture);
  const approvalStage = useWorkflowStore((state) => state.approvalStage);
  const appendLog = useWorkflowStore((state) => state.appendLog);

  const [approvalNote, setApprovalNote] = useState("");
  const [changeScope, setChangeScope] =
    useState<ChangeRequestScope>("architecture");
  const [changeFeedback, setChangeFeedback] = useState("");
  const [pendingAction, setPendingAction] = useState<
    "approve" | "request_changes" | null
  >(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const isAwaitingArchitectureApproval =
    status === "awaiting_approval" &&
    approvalStage === "architecture" &&
    Boolean(workflowId);

  useEffect(() => {
    if (!isAwaitingArchitectureApproval) {
      setPendingAction(null);
      setActionError(null);
    }
  }, [isAwaitingArchitectureApproval]);

  async function handleApprove() {
    if (!workflowId) {
      return;
    }

    setPendingAction("approve");
    setActionError(null);

    try {
      const response = await approveWorkflow(
        workflowId,
        approvalNote.trim() || undefined
      );
      appendLog(response.message);
      setApprovalNote("");
      setChangeFeedback("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleRequestChanges() {
    if (!workflowId) {
      return;
    }

    const feedback = changeFeedback.trim();

    if (!feedback) {
      setActionError("Feedback is required to request plan changes.");
      return;
    }

    setPendingAction("request_changes");
    setActionError(null);

    try {
      const response = await requestWorkflowChanges(
        workflowId,
        changeScope,
        feedback
      );
      appendLog(response.message);
      setApprovalNote("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setPendingAction(null);
    }
  }

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
          {isAwaitingArchitectureApproval ? (
            <div className="approvalBanner">
              <div>
                <h3>Architecture Approval Required</h3>
                <p>
                  The workflow is paused before code generation. Approve this
                  plan or request changes to regenerate requirements or
                  architecture.
                </p>
              </div>

              <div className="approvalControls">
                <label className="approvalField">
                  <span>Approval note</span>
                  <textarea
                    value={approvalNote}
                    onChange={(event) => setApprovalNote(event.target.value)}
                    placeholder="Optional note for the code generation step."
                  />
                </label>

                <label className="approvalField">
                  <span>Change scope</span>
                  <select
                    value={changeScope}
                    onChange={(event) =>
                      setChangeScope(event.target.value as ChangeRequestScope)
                    }
                  >
                    <option value="architecture">Architecture</option>
                    <option value="requirements">Requirements</option>
                  </select>
                </label>

                <label className="approvalField">
                  <span>Request changes</span>
                  <textarea
                    value={changeFeedback}
                    onChange={(event) => setChangeFeedback(event.target.value)}
                    placeholder="Describe what should change before code generation."
                  />
                </label>

                <div className="approvalActions">
                  <button
                    type="button"
                    onClick={handleApprove}
                    disabled={pendingAction !== null}
                  >
                    {pendingAction === "approve" ? "Approving..." : "Approve"}
                  </button>

                  <button
                    type="button"
                    className="secondaryButton"
                    onClick={handleRequestChanges}
                    disabled={pendingAction !== null}
                  >
                    {pendingAction === "request_changes"
                      ? "Requesting..."
                      : "Request Changes"}
                  </button>
                </div>

                {actionError ? (
                  <p className="approvalError">{actionError}</p>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="planSection">
            <h3>{requirements.appName}</h3>
            <p>{requirements.summary}</p>
          </div>

          <div className="planSection">
            <h3>Features</h3>
            <ul>
              {requirements.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
          </div>

          <div className="planSection">
            <h3>Constraints</h3>
            <ul>
              {requirements.constraints.map((constraint) => (
                <li key={constraint}>{constraint}</li>
              ))}
            </ul>
          </div>

          <div className="planSection">
            <h3>Stack</h3>
            <dl className="planDefinitionList">
              <div>
                <dt>Frontend</dt>
                <dd>{architecture.stack.frontend}</dd>
              </div>
              <div>
                <dt>Language</dt>
                <dd>{architecture.stack.language}</dd>
              </div>
              <div>
                <dt>Styling</dt>
                <dd>{architecture.stack.styling}</dd>
              </div>
              <div>
                <dt>Build Tool</dt>
                <dd>{architecture.stack.buildTool}</dd>
              </div>
              <div>
                <dt>State</dt>
                <dd>{architecture.stack.stateManagement}</dd>
              </div>
            </dl>
          </div>

          <div className="planSection">
            <h3>Components</h3>
            <ul>
              {architecture.components.map((component) => (
                <li key={component.name}>
                  <strong>{component.name}</strong>: {component.responsibility}
                </li>
              ))}
            </ul>
          </div>

          <div className="planSection">
            <h3>Data Models</h3>

            {architecture.dataModels.length === 0 ? (
              <p>No data models were returned for this workflow.</p>
            ) : (
              <div className="planModelList">
                {architecture.dataModels.map((model) => (
                  <div key={model.name} className="planModelCard">
                    <h4>{model.name}</h4>
                    <ul>
                      {model.fields.map((field) => (
                        <li key={field.name}>
                          <strong>{field.name}</strong>: {field.type}
                          {field.required ? " required" : " optional"}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
