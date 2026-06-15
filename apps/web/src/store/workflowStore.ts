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
      detail: "Waiting for prompt"
    },
    {
      id: "architecture",
      name: "Architecture Agent",
      status: "pending",
      detail: "Waiting for requirements"
    },
    {
      id: "code",
      name: "Code Generation Agent",
      status: "pending",
      detail: "Waiting for architecture"
    },
    {
      id: "preview",
      name: "Live Preview",
      status: "pending",
      detail: "Preview comes in a later phase"
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
  previewUrl?: string;
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
  logs: ["Phase 2 shell ready. Submit a prompt to run the mock workflow."],
  previewUrl: undefined,
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
      logs: ["Submitting prompt to FastAPI..."],
      agentEvents: [
        {
          id: "requirements",
          name: "Requirements Agent",
          status: "running",
          detail: "Preparing to extract requirements"
        },
        {
          id: "architecture",
          name: "Architecture Agent",
          status: "pending",
          detail: "Waiting for requirements"
        },
        {
          id: "code",
          name: "Code Generation Agent",
          status: "pending",
          detail: "Waiting for architecture"
        },
        {
          id: "preview",
          name: "Live Preview",
          status: "pending",
          detail: "Preview comes in a later phase"
        }
      ]
    });
  },

  workflowStarted: (response) => {
    set((state) => ({
      status: "completed",
      workflowId: response.workflowId,
      requirements: response.requirements,
      architecture: response.architecture,
      files: response.files,
      previewUrl: response.previewUrl ?? undefined,
      logs: [
        ...state.logs,
        ...response.logs,
        `Returned ${response.files.length} generated files to the UI.`
      ],
      agentEvents: [
        {
          id: "requirements",
          name: "Requirements Agent",
          status: "completed",
          detail: `${response.requirements.features.length} features identified`
        },
        {
          id: "architecture",
          name: "Architecture Agent",
          status: "completed",
          detail: `${response.architecture.components.length} components planned`
        },
        {
          id: "code",
          name: "Code Generation Agent",
          status: "completed",
          detail: `${response.files.length} files generated in memory`
        },
        {
          id: "preview",
          name: "Live Preview",
          status: response.previewUrl ? "completed" : "pending",
          detail: response.previewUrl
            ? "Preview URL received"
            : "Preview will be added after local runner phase"
        }
      ]
    }));
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