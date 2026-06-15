import { create } from "zustand";
import type {
  AgentEvent,
  AgentStatus,
  ArchitectureSpec,
  GeneratedFile,
  RequirementsSpec,
  WorkflowResponse,
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
      id: "files",
      name: "File Writer",
      status: "pending",
      detail: "Waiting to write generated files"
    },
    {
      id: "preview",
      name: "Live Preview",
      status: "pending",
      detail: "Preview is not available until a later phase"
    }
  ];
}

interface WorkflowStore {
  prompt: string;
  status: WorkflowStatus;
  workflowId?: string;
  requirements?: RequirementsSpec;
  architecture?: ArchitectureSpec;
  files: GeneratedFile[];
  logs: string[];
  previewUrl?: string | null;
  workspacePath?: string | null;
  agentEvents: AgentEvent[];

  setPrompt: (prompt: string) => void;
  resetWorkflow: () => void;
  beginSubmission: () => void;
  workflowStarted: (response: WorkflowResponse) => void;
  failWorkflow: (message: string) => void;
  setPreviewUrl: (url: string) => void;
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
  files: [],
  logs: ["Phase 3 shell ready."],
  previewUrl: undefined,
  workspacePath: undefined,
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
      files: [],
      logs: ["Workflow reset."],
      previewUrl: undefined,
      workspacePath: undefined,
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
      agentEvents: state.agentEvents.map((agent) =>
        agent.id === id
          ? {
              ...agent,
              status,
              detail
            }
          : agent
      )
    }));
  },

  beginSubmission: () => {
    set({
      status: "submitting",
      workflowId: undefined,
      requirements: undefined,
      architecture: undefined,
      files: [],
      previewUrl: undefined,
      workspacePath: undefined,
      logs: ["Submitting prompt to FastAPI workflow engine..."],
      agentEvents: defaultAgentEvents().map((agent) => {
        if (agent.id === "requirements") {
          return {
            ...agent,
            status: "running",
            detail: "Analyzing user prompt"
          };
        }

        return agent;
      })
    });
  },

  workflowStarted: (response) => {
    const requirementSummary = [
      `Requirements: ${response.requirements.features.length} features, ${response.requirements.constraints.length} constraints.`
    ];

    const architectureSummary = [
      `Architecture: ${response.architecture.stack.frontend} + ${response.architecture.stack.buildTool}.`,
      `Components: ${response.architecture.components
        .map((component) => component.name)
        .join(", ")}.`
    ];

    const fileSummary = response.files.map((file) => `Generated file: ${file.path}`);

    const workspaceSummary = response.workspacePath
      ? [`Workspace path: ${response.workspacePath}`]
      : [];

    set({
      status: response.status,
      workflowId: response.workflowId,
      requirements: response.requirements,
      architecture: response.architecture,
      files: response.files,
      previewUrl: response.previewUrl ?? undefined,
      workspacePath: response.workspacePath ?? undefined,
      logs: [
        ...response.logs,
        ...requirementSummary,
        ...architectureSummary,
        ...fileSummary,
        ...workspaceSummary
      ],
      agentEvents: defaultAgentEvents().map((agent) => {
        if (agent.id === "requirements") {
          return {
            ...agent,
            status: "completed",
            detail: `${response.requirements.features.length} features extracted`
          };
        }

        if (agent.id === "architecture") {
          return {
            ...agent,
            status: "completed",
            detail: `${response.architecture.components.length} components planned`
          };
        }

        if (agent.id === "code") {
          return {
            ...agent,
            status: "completed",
            detail: `${response.files.length} files generated`
          };
        }

        if (agent.id === "files") {
          return {
            ...agent,
            status: response.workspacePath ? "completed" : "pending",
            detail: response.workspacePath
              ? `Files written to ${response.workspacePath}`
              : "Files have not been written yet"
          };
        }

        if (agent.id === "preview") {
          return {
            ...agent,
            status: response.previewUrl ? "completed" : "pending",
            detail: response.previewUrl
              ? "Preview URL received"
              : "Preview will be added after local runner phase"
          };
        }

        return agent;
      })
    });
  },

  failWorkflow: (message) => {
    set((state) => ({
      status: "failed",
      logs: [...state.logs, `Error: ${message}`],
      agentEvents: state.agentEvents.map((agent) =>
        agent.status === "running"
          ? {
              ...agent,
              status: "failed",
              detail: message
            }
          : agent
      )
    }));
  },

  setPreviewUrl: (url) => {
    set({
      previewUrl: url,
      status: "preview_ready"
    });
  }
}));