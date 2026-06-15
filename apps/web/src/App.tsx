import { AgentTimeline } from "./components/AgentTimeline";
import { BuildLogs } from "./components/BuildLogs";
import { FileTree } from "./components/FileTree";
import { PlanSummary } from "./components/PlanSummary";
import { PreviewPane } from "./components/PreviewPane";
import { PromptBar } from "./components/PromptBar";
import { StatusBar } from "./components/StatusBar";
import "./App.css";

function App() {
  return (
    <main className="appShell">
      <PromptBar />
      <StatusBar />

      <section className="workspaceGrid">
        <div className="leftColumn">
          <AgentTimeline />
          <BuildLogs />
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