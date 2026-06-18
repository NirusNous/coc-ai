import { useEffect, useState } from "react";
import { createProject, listProjects } from "../api/workflows";
import { useWorkflowStore } from "../store/workflowStore";
import type { ProjectResponse } from "../types/workflow";

export function ProjectSidebar() {
  const selectedProjectId = useWorkflowStore(
    (state) => state.selectedProjectId
  );
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const status = useWorkflowStore((state) => state.status);
  const previewAction = useWorkflowStore((state) => state.previewAction);
  const setSelectedProjectId = useWorkflowStore(
    (state) => state.setSelectedProjectId
  );

  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isBusy =
    status === "submitting" ||
    status === "queued" ||
    status === "running" ||
    status === "awaiting_approval" ||
    status === "code_generated" ||
    status === "files_written" ||
    status === "preview_restarting" ||
    previewAction !== null;

  useEffect(() => {
    let isCancelled = false;

    async function loadProjects() {
      setIsLoading(true);

      try {
        const response = await listProjects();

        if (isCancelled) {
          return;
        }

        setProjects(response.projects);
        setError(null);

        if (
          response.projects.length > 0 &&
          (!selectedProjectId ||
            !response.projects.some(
              (project) => project.projectId === selectedProjectId
            ))
        ) {
          setSelectedProjectId(response.projects[0].projectId);
        }
      } catch (loadError) {
        if (!isCancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : String(loadError)
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadProjects();

    return () => {
      isCancelled = true;
    };
  }, [selectedProjectId, setSelectedProjectId, workflowId, status]);

  async function handleCreateProject() {
    const name = projectName.trim();

    if (!name) {
      setError("Project name is required.");
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      const project = await createProject(
        name,
        projectDescription.trim() || undefined
      );
      setProjects((current) => [project, ...current]);
      setSelectedProjectId(project.projectId);
      setProjectName("");
      setProjectDescription("");
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : String(createError)
      );
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <section className="panel projectSidebar">
      <div className="panelHeader">
        <h2>Projects</h2>
      </div>

      <div className="projectCreateForm">
        <input
          value={projectName}
          onChange={(event) => setProjectName(event.target.value)}
          placeholder="New project name"
        />
        <textarea
          value={projectDescription}
          onChange={(event) => setProjectDescription(event.target.value)}
          placeholder="Optional description"
        />
        <button
          type="button"
          className="secondaryButton"
          onClick={handleCreateProject}
          disabled={isCreating}
        >
          {isCreating ? "Creating..." : "Create Project"}
        </button>
      </div>

      {isLoading ? (
        <div className="emptyState">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="emptyState">
          Create a project to start organizing workflows.
        </div>
      ) : (
        <div className="projectList">
          {projects.map((project) => (
            <button
              key={project.projectId}
              type="button"
              className={`projectItem ${
                project.projectId === selectedProjectId ? "selected" : ""
              }`}
              disabled={isBusy}
              onClick={() => setSelectedProjectId(project.projectId)}
            >
              <div className="projectHeader">
                <strong>{project.name}</strong>
                <span>{project.workflowCount}</span>
              </div>
              <p>{project.description ?? "No description"}</p>
            </button>
          ))}
        </div>
      )}

      {error ? <p className="historyError">{error}</p> : null}
    </section>
  );
}
