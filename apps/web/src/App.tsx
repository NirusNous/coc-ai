import { AgentTimeline } from "./components/AgentTimeline";
import { BuildLogs } from "./components/BuildLogs";
import { FileTree } from "./components/FileTree";
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

        <FileTree />
        <PreviewPane />
      </section>
    </main>
  );
}

export default App;