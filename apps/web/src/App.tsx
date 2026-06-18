import { AttemptHistory } from "./components/AttemptHistory";
import { AgentTimeline } from "./components/AgentTimeline";
import { FileTree } from "./components/FileTree";
import { LogsPanel } from "./components/LogsPanel";
import { PlanSummary } from "./components/PlanSummary";
import { PreviewPane } from "./components/PreviewPane";
import { ProjectSidebar } from "./components/ProjectSidebar";
import { PromptBar } from "./components/PromptBar";
import { StatusBar } from "./components/StatusBar";
import { WorkflowHistory } from "./components/WorkflowHistory";
import "./App.css";

function App() {
  return (
    <main className="appShell">
      <PromptBar />
      <StatusBar />

      <section className="workspaceGrid">
        <div className="leftColumn">
          <ProjectSidebar />
          <AgentTimeline />
          <AttemptHistory />
          <WorkflowHistory />
          <LogsPanel />
        </div>

        <div className="middleColumn">
          <PlanSummary />
          <FileTree />
        </div>

        <PreviewPane />
      </section>
    </main>
  );
}

export default App;
