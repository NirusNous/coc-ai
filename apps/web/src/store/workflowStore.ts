import { create } from "zustand";
import type {
  AgentEvent,
  AgentStatus,
  GeneratedFile,
  WorkflowResponse,
  WorkflowStatus
} from "../types/workflow";

function defaultAgentEvents(): AgentEvent[] {
  return [
    {
      id: "prompt",
      name: "Prompt Intake",
      status: "pending",
      detail: "Waiting for a user prompt"
    },
    {
      id: "api",
      name: "FastAPI Backend",
      status: "pending",
      detail: "Waiting for request"
    },
    {
      id: "workflow",
      name: "Workflow Engine",
      status: "pending",
      detail: "Phase 2 will run the workflow here"
    },
    {
      id: "preview",
      name: "Live Preview",
      status: "pending",
      detail: "No generated app yet"
    }
  ];
}

interface WorkflowStore {
  prompt: string;
  status: WorkflowStatus;
  workflowId?: string;
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
  files: [],
  logs: ["Phase 1 shell ready."],
  previewUrl: undefined,
  agentEvents: defaultAgentEvents(),

  setPrompt: (prompt) => {
    set({ prompt });
  },

  resetWorkflow: () => {
    set({
      status: "idle",
      workflowId: undefined,
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
      files: [],
      previewUrl: undefined,
      logs: ["Submitting prompt to FastAPI..."],
      agentEvents: defaultAgentEvents().map((agent) => {
        if (agent.id === "prompt") {
          return {
            ...agent,
            status: "completed",
            detail: "Prompt captured by the UI"
          };
        }

        if (agent.id === "api") {
          return {
            ...agent,
            status: "running",
            detail: "Sending request to backend"
          };
        }

        return agent;
      })
    });
  },

  workflowStarted: (response) => {
    set((state) => ({
      status: "started",
      workflowId: response.workflowId,
      files: response.files ?? [],
      previewUrl: response.previewUrl,
      logs: [
        ...state.logs,
        `Workflow ${response.workflowId} started.`,
        `Prompt: ${response.prompt}`
      ],
      agentEvents: state.agentEvents.map((agent) => {
        if (agent.id === "api") {
          return {
            ...agent,
            status: "completed",
            detail: "FastAPI accepted the prompt"
          };
        }

        if (agent.id === "workflow") {
          return {
            ...agent,
            status: "completed",
            detail: "Workflow placeholder created"
          };
        }

        if (agent.id === "preview") {
          return {
            ...agent,
            status: response.previewUrl ? "completed" : "pending",
            detail: response.previewUrl
              ? "Preview URL received"
              : "Preview will be added in a later phase"
          };
        }

        return agent;
      })
    }));
  },

  failWorkflow: (message) => {
    set((state) => ({
      status: "failed",
      logs: [...state.logs, `Error: ${message}`],
      agentEvents: state.agentEvents.map((agent) =>
        agent.id === "api"
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