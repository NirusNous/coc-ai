import { create } from "zustand";
import type {
  ApprovalStage,
  AgentEvent,
  AgentStatus,
  ArchitectureSpec,
  BuildAttempt,
  GeneratedFile,
  PreviewAction,
  RequirementsSpec,
  WorkflowResponse,
  WorkflowSocketEvent,
  WorkflowStartResponse,
  WorkflowStatus
} from "../types/workflow";

function defaultAgentEvents(): AgentEvent[] {
  return [
    {
      id: "requirements",
      name: "Requirements Agent",
      status: "pending",
      detail: "Waiting to convert prompt into requirements"
    },
    {
      id: "architecture",
      name: "Architecture Agent",
      status: "pending",
      detail: "Waiting to design the app structure"
    },
    {
      id: "code",
      name: "Code Generation Agent",
      status: "pending",
      detail: "Waiting to generate source files"
    },
    {
      id: "build",
      name: "Build/Test Agent",
      status: "pending",
      detail: "Waiting to validate install and build stages"
    },
    {
      id: "debug",
      name: "Debug Agent",
      status: "pending",
      detail: "Waiting to analyze any failed validation attempts"
    },
    {
      id: "patch",
      name: "Patch Agent",
      status: "pending",
      detail: "Waiting to rewrite files for retry attempts"
    },
    {
      id: "files",
      name: "File Writer",
      status: "pending",
      detail: "Waiting to write generated files"
    },
    {
      id: "preview",
      name: "Live Preview",
      status: "pending",
      detail: "Waiting to start generated app"
    }
  ];
}

function isBuildFailureStatus(status: WorkflowStatus): boolean {
  return (
    status === "install_failed" ||
    status === "build_failed" ||
    status === "timeout"
  );
}

function isPreviewFailureStatus(status: WorkflowStatus): boolean {
  return status === "preview_failed" || status === "runtime_crashed";
}

function updateAgent(
  agentEvents: AgentEvent[],
  id: string,
  status: AgentStatus,
  detail: string
): AgentEvent[] {
  return agentEvents.map((agent) =>
    agent.id === id
      ? {
          ...agent,
          status,
          detail
        }
      : agent
  );
}

function failRunningAgents(
  agentEvents: AgentEvent[],
  detail: string
): AgentEvent[] {
  return agentEvents.map((agent) =>
    agent.status === "running"
      ? {
          ...agent,
          status: "failed",
          detail
        }
      : agent
  );
}

function upsertAttempt(
  attempts: BuildAttempt[],
  nextAttempt: BuildAttempt
): BuildAttempt[] {
  if (
    attempts.some(
      (attempt) => attempt.attemptNumber === nextAttempt.attemptNumber
    )
  ) {
    return attempts.map((attempt) =>
      attempt.attemptNumber === nextAttempt.attemptNumber
        ? nextAttempt
        : attempt
    );
  }

  return [...attempts, nextAttempt].sort(
    (left, right) => left.attemptNumber - right.attemptNumber
  );
}

function hydrateAgentEvents(workflow: WorkflowResponse): AgentEvent[] {
  let agentEvents = defaultAgentEvents();

  if (workflow.requirements) {
    agentEvents = updateAgent(
      agentEvents,
      "requirements",
      "completed",
      `${workflow.requirements.features.length} features extracted`
    );
  }

  if (workflow.architecture) {
    agentEvents = updateAgent(
      agentEvents,
      "architecture",
      "completed",
      `${workflow.architecture.components.length} components planned`
    );
  }

  if (workflow.status === "awaiting_approval") {
    agentEvents = updateAgent(
      agentEvents,
      "code",
      "pending",
      "Waiting for architecture approval before code generation."
    );
  }

  if (workflow.files.length > 0) {
    agentEvents = updateAgent(
      agentEvents,
      "code",
      "completed",
      `${workflow.files.length} files generated`
    );
  }

  if (workflow.attempts.some((attempt) => attempt.debugSummary)) {
    const latestDebugAttempt = [...workflow.attempts]
      .reverse()
      .find((attempt) => attempt.debugSummary);

    if (latestDebugAttempt?.debugSummary) {
      agentEvents = updateAgent(
        agentEvents,
        "debug",
        "completed",
        latestDebugAttempt.debugSummary
      );
    }
  }

  if (workflow.attempts.length > 1) {
    const patchDetail = workflow.isRetrying
      ? `Preparing attempt ${workflow.currentAttempt}/${workflow.maxAttempts}`
      : `Applied patches through attempt ${workflow.attempts.length}`;

    agentEvents = updateAgent(
      agentEvents,
      "patch",
      workflow.isRetrying ? "running" : "completed",
      patchDetail
    );
  }

  if (workflow.workspacePath) {
    agentEvents = updateAgent(
      agentEvents,
      "files",
      "completed",
      `Files written to ${workflow.workspacePath}`
    );
  }

  if (workflow.attempts.length > 0) {
    const latestAttempt = workflow.attempts[workflow.attempts.length - 1];

    if (
      latestAttempt.status === "preview_ready" ||
      latestAttempt.status === "preview_failed" ||
      latestAttempt.status === "runtime_crashed"
    ) {
      agentEvents = updateAgent(
        agentEvents,
        "build",
        "completed",
        `Validation completed on attempt ${latestAttempt.attemptNumber}/${workflow.maxAttempts}`
      );
    } else if (isBuildFailureStatus(latestAttempt.status)) {
      agentEvents = updateAgent(
        agentEvents,
        "build",
        "failed",
        `Validation ended with ${latestAttempt.status}.`
      );
    }
  } else if (workflow.workspacePath) {
    agentEvents = updateAgent(
      agentEvents,
      "build",
      "pending",
      "Waiting for runner validation to start"
    );
  }

  if (workflow.isRetrying) {
    return updateAgent(
      agentEvents,
      "build",
      "running",
      `Retrying attempt ${workflow.currentAttempt}/${workflow.maxAttempts}`
    );
  }

  if (workflow.status === "preview_ready" && workflow.previewUrl) {
    return updateAgent(
      updateAgent(
        agentEvents,
        "build",
        "completed",
        `Validation completed on attempt ${workflow.currentAttempt}/${workflow.maxAttempts}`
      ),
      "preview",
      "completed",
      `Preview ready at ${workflow.previewUrl}`
    );
  }

  if (workflow.status === "preview_stopped") {
    return updateAgent(
      updateAgent(
        agentEvents,
        "build",
        "completed",
        "Validation completed. Preview can be restarted."
      ),
      "preview",
      "completed",
      "Preview stopped. Ready to restart."
    );
  }

  if (workflow.status === "workspace_cleaned") {
    return updateAgent(
      updateAgent(
        agentEvents,
        "build",
        "completed",
        "Validation completed before workspace cleanup."
      ),
      "preview",
      "pending",
      "Workspace cleaned. Generate a new app to preview again."
    );
  }

  if (isBuildFailureStatus(workflow.status)) {
    return updateAgent(
      agentEvents,
      "build",
      "failed",
      `Workflow ended with ${workflow.status}.`
    );
  }

  if (
    isPreviewFailureStatus(workflow.status) ||
    workflow.status === "failed"
  ) {
    return updateAgent(
      updateAgent(
        agentEvents,
        "build",
        "completed",
        "Validation passed before preview startup failed."
      ),
      "preview",
      "failed",
      `Workflow ended with ${workflow.status}.`
    );
  }

  if (
    workflow.status === "files_written" ||
    workflow.status === "preview_restarting"
  ) {
    return updateAgent(
      agentEvents,
      "build",
      "running",
      workflow.status === "preview_restarting"
        ? "Re-running build validation before preview restart"
        : "Runner validation pending."
    );
  }

  return agentEvents;
}

interface WorkflowStore {
  prompt: string;
  status: WorkflowStatus;
  workflowId?: string;
  requirements?: RequirementsSpec;
  architecture?: ArchitectureSpec;
  approvalStage?: ApprovalStage | null;
  files: GeneratedFile[];
  attempts: BuildAttempt[];
  currentAttempt: number;
  maxAttempts: number;
  isRetrying: boolean;
  logs: string[];
  previewUrl?: string | null;
  previewPort?: number | null;
  workspacePath?: string | null;
  previewAction: PreviewAction | null;
  agentEvents: AgentEvent[];

  setPrompt: (prompt: string) => void;
  resetWorkflow: () => void;
  beginSubmission: () => void;
  workflowQueued: (response: WorkflowStartResponse) => void;
  restoreWorkflow: (workflow: WorkflowResponse) => void;
  beginPreviewAction: (action: PreviewAction, message: string) => void;
  handleWorkflowEvent: (event: WorkflowSocketEvent) => void;
  failWorkflow: (message: string) => void;
  failPreviewAction: (message: string) => void;
  appendLog: (line: string) => void;
  setAgentStatus: (
    id: string,
    status: AgentStatus,
    detail: string
  ) => void;
}

export const useWorkflowStore = create<WorkflowStore>((set) => ({
  prompt: "",
  status: "idle",
  workflowId: undefined,
  requirements: undefined,
  architecture: undefined,
  approvalStage: undefined,
  files: [],
  attempts: [],
  currentAttempt: 1,
  maxAttempts: 3,
  isRetrying: false,
  logs: ["Workflow workspace ready."],
  previewUrl: undefined,
  previewPort: undefined,
  workspacePath: undefined,
  previewAction: null,
  agentEvents: defaultAgentEvents(),

  setPrompt: (prompt) => {
    set({ prompt });
  },

  resetWorkflow: () => {
    set({
      status: "idle",
      workflowId: undefined,
      requirements: undefined,
      architecture: undefined,
      approvalStage: undefined,
      files: [],
      attempts: [],
      currentAttempt: 1,
      maxAttempts: 3,
      isRetrying: false,
      logs: ["Workflow reset."],
      previewUrl: undefined,
      previewPort: undefined,
      workspacePath: undefined,
      previewAction: null,
      agentEvents: defaultAgentEvents()
    });
  },

  appendLog: (line) => {
    set((state) => ({
      logs: [...state.logs, line]
    }));
  },

  setAgentStatus: (id, status, detail) => {
    set((state) => ({
      agentEvents: updateAgent(state.agentEvents, id, status, detail)
    }));
  },

  beginSubmission: () => {
    set({
      status: "submitting",
      workflowId: undefined,
      requirements: undefined,
      architecture: undefined,
      approvalStage: undefined,
      files: [],
      attempts: [],
      currentAttempt: 1,
      maxAttempts: 3,
      isRetrying: false,
      previewUrl: undefined,
      previewPort: undefined,
      workspacePath: undefined,
      previewAction: null,
      logs: ["Submitting prompt to FastAPI..."],
      agentEvents: defaultAgentEvents()
    });
  },

  workflowQueued: (response) => {
    set({
      status: "queued",
      workflowId: response.workflowId,
      currentAttempt: 1,
      maxAttempts: 3,
      isRetrying: false,
      previewAction: null,
      logs: [
        `Workflow ${response.workflowId} queued.`,
        "Opening workflow event stream..."
      ]
    });
  },

  restoreWorkflow: (workflow) => {
    set({
      prompt: workflow.prompt,
      status: workflow.status,
      workflowId: workflow.workflowId,
      requirements: workflow.requirements ?? undefined,
      architecture: workflow.architecture ?? undefined,
      approvalStage: workflow.approvalStage ?? undefined,
      files: workflow.files ?? [],
      attempts: workflow.attempts ?? [],
      currentAttempt: workflow.currentAttempt ?? 1,
      maxAttempts: workflow.maxAttempts ?? 3,
      isRetrying: workflow.isRetrying ?? false,
      logs: workflow.logs ?? [],
      previewUrl: workflow.previewUrl ?? undefined,
      previewPort: workflow.previewPort ?? undefined,
      workspacePath: workflow.workspacePath ?? undefined,
      previewAction: null,
      agentEvents: hydrateAgentEvents(workflow)
    });
  },

  beginPreviewAction: (action, message) => {
    set((state) => ({
      previewAction: action,
      status:
        action === "restarting"
          ? "preview_restarting"
          : state.status,
      approvalStage:
        action === "restarting"
          ? undefined
          : state.approvalStage,
      isRetrying: false,
      logs: [...state.logs, message],
      agentEvents:
        action === "restarting"
          ? updateAgent(
              updateAgent(
                state.agentEvents,
                "preview",
                "pending",
                "Waiting for preview runtime to restart after validation."
              ),
              "build",
              "running",
              "Restarting preview and re-running validation"
            )
          : state.agentEvents
    }));
  },

  handleWorkflowEvent: (event) => {
    set((state) => {
      const { type, payload } = event;

      if (type === "workflow:started") {
        return {
          status: "running",
          approvalStage: payload.approvalStage ?? undefined,
          currentAttempt: payload.currentAttempt ?? state.currentAttempt,
          maxAttempts: payload.maxAttempts ?? state.maxAttempts,
          isRetrying: payload.isRetrying ?? false,
          logs: [...state.logs, "Workflow started."]
        };
      }

      if (type === "log") {
        return {
          logs: [...state.logs, payload.message]
        };
      }

      if (type === "workflow:awaiting_approval") {
        return {
          status: "awaiting_approval",
          workflowId: payload.workflowId ?? state.workflowId,
          requirements: payload.requirements ?? state.requirements,
          architecture: payload.architecture ?? state.architecture,
          approvalStage: payload.approvalStage ?? "architecture",
          previewAction: null,
          isRetrying: false,
          agentEvents: updateAgent(
            state.agentEvents,
            "code",
            "pending",
            "Waiting for architecture approval before code generation."
          )
        };
      }

      if (type === "attempt:started") {
        return {
          status: "running",
          currentAttempt: payload.attemptNumber,
          maxAttempts: payload.maxAttempts,
          isRetrying: payload.isRetrying,
          agentEvents:
            updateAgent(
              updateAgent(
                state.agentEvents,
                "preview",
                "pending",
                "Waiting for preview runtime after validation."
              ),
              "build",
              "running",
              payload.isRetrying
                ? `Retrying attempt ${payload.attemptNumber}/${payload.maxAttempts}`
                : `Validating attempt ${payload.attemptNumber}/${payload.maxAttempts}`
            )
        };
      }

      if (type === "attempt:completed") {
        return {
          attempts: upsertAttempt(state.attempts, payload.attempt),
          currentAttempt: payload.attempt.attemptNumber,
          maxAttempts: payload.maxAttempts,
          isRetrying: payload.willRetry
        };
      }

      if (type === "attempt:retrying") {
        return {
          status: "running",
          currentAttempt: payload.nextAttemptNumber,
          maxAttempts: payload.maxAttempts,
          isRetrying: true,
          logs: [...state.logs, payload.message],
          agentEvents: updateAgent(
            updateAgent(
              updateAgent(
                updateAgent(
                  state.agentEvents,
                  "debug",
                  "completed",
                  payload.debugSummary
                ),
                "patch",
                "running",
                `Preparing attempt ${payload.nextAttemptNumber}/${payload.maxAttempts}`
              ),
              "preview",
              "pending",
              "Waiting for retry validation to finish."
            ),
            "build",
            "running",
            `Preparing attempt ${payload.nextAttemptNumber}/${payload.maxAttempts}`
          )
        };
      }

      if (type === "agent:started") {
        return {
          agentEvents: updateAgent(
            state.agentEvents,
            payload.agentId,
            "running",
            payload.detail
          )
        };
      }

      if (type === "agent:completed") {
        const nextState: Partial<WorkflowStore> = {
          agentEvents: updateAgent(
            state.agentEvents,
            payload.agentId,
            "completed",
            payload.detail
          )
        };

        if (payload.agentId === "requirements" && payload.output) {
          nextState.requirements = payload.output;
        }

        if (payload.agentId === "architecture" && payload.output) {
          nextState.architecture = payload.output;
        }

        return nextState;
      }

      if (type === "agent:failed") {
        return {
          previewAction: null,
          agentEvents: updateAgent(
            state.agentEvents,
            payload.agentId,
            "failed",
            payload.detail
          )
        };
      }

      if (type === "code:generated") {
        return {
          status: "code_generated",
          approvalStage: undefined,
          files: payload.files ?? []
        };
      }

      if (type === "files:written") {
        return {
          status: "files_written",
          approvalStage: undefined,
          workspacePath: payload.workspacePath
        };
      }

      if (type === "runner:stage") {
        const agentId = payload.stage === "preview" ? "preview" : "build";
        const nextStatus =
          payload.status === "failed"
            ? "failed"
            : payload.status === "completed"
              ? "completed"
              : "running";

        return {
          isRetrying: state.isRetrying,
          agentEvents: updateAgent(
            state.agentEvents,
            agentId,
            nextStatus,
            payload.detail
          )
        };
      }

      if (type === "preview:ready") {
        return {
          status: "preview_ready",
          approvalStage: undefined,
          currentAttempt: payload.attemptNumber ?? state.currentAttempt,
          isRetrying: false,
          previewUrl: payload.previewUrl,
          previewPort: payload.previewPort,
          previewAction: null,
          agentEvents: updateAgent(
            updateAgent(
              state.agentEvents,
              "build",
              "completed",
              `Validation completed on attempt ${(payload.attemptNumber ?? state.currentAttempt)}/${state.maxAttempts}`
            ),
            "preview",
            "completed",
            `Preview ready at ${payload.previewUrl}`
          )
        };
      }

      if (type === "preview:failed") {
        const nextAgentEvents = isBuildFailureStatus(payload.status)
          ? updateAgent(
              state.agentEvents,
              "build",
              "failed",
              payload.message
            )
          : updateAgent(
              updateAgent(
                state.agentEvents,
                "build",
                "completed",
                "Validation passed before preview startup failed."
              ),
              "preview",
              "failed",
              payload.message
            );

        return {
          status: payload.status,
          approvalStage: undefined,
          currentAttempt: payload.attemptNumber ?? state.currentAttempt,
          isRetrying: false,
          previewUrl: undefined,
          previewPort: undefined,
          previewAction: null,
          agentEvents: nextAgentEvents
        };
      }

      if (type === "preview:stopped") {
        if (payload.reason === "restart") {
          return {
            status: "preview_restarting",
            approvalStage: undefined,
            isRetrying: false,
            previewUrl: undefined,
            previewPort: undefined,
            previewAction: "restarting",
            agentEvents: updateAgent(
              updateAgent(
                state.agentEvents,
                "preview",
                "pending",
                "Waiting for preview runtime to restart after validation."
              ),
              "build",
              "running",
              "Restarting preview and re-running validation"
            )
          };
        }

        return {
          status: "preview_stopped",
          approvalStage: undefined,
          isRetrying: false,
          previewUrl: undefined,
          previewPort: undefined,
          previewAction:
            payload.reason === "clean" && state.previewAction === "cleaning"
              ? "cleaning"
              : null,
          agentEvents: updateAgent(
            updateAgent(
              state.agentEvents,
              "build",
              "completed",
              "Validation completed."
            ),
            "preview",
            "completed",
            payload.reason === "clean"
              ? "Preview stopped for workspace cleanup"
              : "Preview stopped. Ready to restart."
          )
        };
      }

      if (type === "workspace:cleaned") {
        return {
          status: "workspace_cleaned",
          approvalStage: undefined,
          isRetrying: false,
          previewUrl: undefined,
          previewPort: undefined,
          workspacePath: undefined,
          previewAction: null,
          agentEvents: updateAgent(
            updateAgent(
              state.agentEvents,
              "preview",
              "pending",
              "Workspace cleaned. Generate a new app to preview again."
            ),
            "build",
            "completed",
            "Validation completed before workspace cleanup."
          )
        };
      }

      if (type === "workflow:completed") {
        return {
          status: payload.status ?? "completed",
          workflowId: payload.workflowId ?? state.workflowId,
          requirements: payload.requirements ?? state.requirements,
          architecture: payload.architecture ?? state.architecture,
          approvalStage: payload.approvalStage ?? undefined,
          files: payload.files ?? state.files,
          attempts: payload.attempts ?? state.attempts,
          currentAttempt: payload.currentAttempt ?? state.currentAttempt,
          maxAttempts: payload.maxAttempts ?? state.maxAttempts,
          isRetrying: payload.isRetrying ?? false,
          previewUrl: payload.previewUrl ?? state.previewUrl,
          previewPort: payload.previewPort ?? state.previewPort,
          workspacePath: payload.workspacePath ?? state.workspacePath,
          previewAction: null
        };
      }

      if (type === "workflow:failed") {
        return {
          status: "failed",
          approvalStage: undefined,
          isRetrying: false,
          previewAction: null,
          logs: [...state.logs, `Error: ${payload.message}`],
          agentEvents: failRunningAgents(state.agentEvents, payload.message)
        };
      }

      return state;
    });
  },

  failWorkflow: (message) => {
    set((state) => ({
      status: "failed",
      approvalStage: undefined,
      isRetrying: false,
      previewAction: null,
      logs: [...state.logs, `Error: ${message}`],
      agentEvents: failRunningAgents(state.agentEvents, message)
    }));
  },

  failPreviewAction: (message) => {
    set((state) => ({
      status:
        state.previewAction === "restarting"
          ? "failed"
          : state.status,
      approvalStage:
        state.previewAction === "restarting"
          ? undefined
          : state.approvalStage,
      previewAction: null,
      isRetrying: false,
      logs: [...state.logs, `Error: ${message}`],
      agentEvents:
        state.previewAction === "restarting"
          ? updateAgent(state.agentEvents, "preview", "failed", message)
          : state.agentEvents
    }));
  }
}));
