import { useWorkflowStore } from "../store/workflowStore";

export function PreviewPane() {
  const previewUrl = useWorkflowStore((state) => state.previewUrl);

  return (
    <section className="panel previewPane">
      <div className="panelHeader">
        <h2>Live Preview</h2>
      </div>

      {previewUrl ? (
        <iframe title="Generated app preview" src={previewUrl} />
      ) : (
        <div className="previewPlaceholder">
          <div>
            <strong>No preview yet</strong>
            <p>
              In a later phase, generated React apps will run locally and appear
              here.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}