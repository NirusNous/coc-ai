import { useWorkflowStore } from "../store/workflowStore";

export function FileTree() {
  const files = useWorkflowStore((state) => state.files);

  return (
    <section className="panel fileTree">
      <div className="panelHeader">
        <h2>File Tree</h2>
      </div>

      {files.length === 0 ? (
        <div className="emptyState">
          Generated files will appear here after the Code Generation Agent runs.
        </div>
      ) : (
        <ul className="fileList">
          {files.map((file) => (
            <li key={file.path}>
              <span className="fileIcon">FILE</span>
              {file.path}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
