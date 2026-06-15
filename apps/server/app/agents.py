import json

from app.models import (
    ArchitectureSpec,
    ComponentSpec,
    DataFieldSpec,
    DataModelSpec,
    GeneratedFile,
    RequirementsSpec,
    StackSpec,
)


def requirements_agent(prompt: str) -> RequirementsSpec:
    return RequirementsSpec(
        appName="Task Manager",
        summary=f"Generated requirements for: {prompt}",
        features=[
            "Create tasks",
            "Mark tasks as complete",
            "Delete tasks",
            "Show empty state when there are no tasks",
        ],
        constraints=[
            "Use React",
            "Use TypeScript",
            "Use Vite",
            "Use client-side state only",
            "Do not require authentication",
            "Do not require a database",
        ],
    )


def architecture_agent(
    prompt: str,
    requirements: RequirementsSpec,
) -> ArchitectureSpec:
    return ArchitectureSpec(
        stack=StackSpec(
            frontend="React",
            language="TypeScript",
            buildTool="Vite",
            styling="CSS",
            stateManagement="React useState",
        ),
        components=[
            ComponentSpec(
                name="App",
                responsibility="Owns task state and renders the full task manager UI",
            ),
            ComponentSpec(
                name="TaskForm",
                responsibility="Captures new task text from the user",
            ),
            ComponentSpec(
                name="TaskList",
                responsibility="Displays active and completed tasks",
            ),
            ComponentSpec(
                name="TaskItem",
                responsibility="Displays one task with complete and delete actions",
            ),
        ],
        dataModels=[
            DataModelSpec(
                name="Task",
                fields=[
                    DataFieldSpec(name="id", type="string", required=True),
                    DataFieldSpec(name="title", type="string", required=True),
                    DataFieldSpec(name="completed", type="boolean", required=True),
                ],
            )
        ],
    )


def code_generation_agent(
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
) -> list[GeneratedFile]:
    package_json = json.dumps(
        {
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": {
                "@vitejs/plugin-react": "latest",
                "vite": "latest",
                "typescript": "latest",
                "react": "latest",
                "react-dom": "latest",
                "@types/react": "latest",
                "@types/react-dom": "latest",
            },
            "devDependencies": {},
        },
        indent=2,
    )

    return [
        GeneratedFile(
            path="package.json",
            content=package_json,
        ),
        GeneratedFile(
            path="index.html",
            content="""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Generated Task Manager</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
        ),
        GeneratedFile(
            path="vite.config.ts",
            content="""import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()]
});
""",
        ),
        GeneratedFile(
            path="tsconfig.json",
            content="""{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": []
}
""",
        ),
        GeneratedFile(
            path="src/main.tsx",
            content="""import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
""",
        ),
        GeneratedFile(
            path="src/App.tsx",
            content="""import { useState } from "react";

interface Task {
  id: string;
  title: string;
  completed: boolean;
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");

  function addTask() {
    const trimmedTitle = title.trim();

    if (!trimmedTitle) {
      return;
    }

    setTasks([
      ...tasks,
      {
        id: crypto.randomUUID(),
        title: trimmedTitle,
        completed: false
      }
    ]);

    setTitle("");
  }

  function toggleTask(id: string) {
    setTasks(
      tasks.map((task) =>
        task.id === id
          ? {
              ...task,
              completed: !task.completed
            }
          : task
      )
    );
  }

  function deleteTask(id: string) {
    setTasks(tasks.filter((task) => task.id !== id));
  }

  return (
    <main className="app">
      <section className="card">
        <p className="eyebrow">Generated App</p>
        <h1>Task Manager</h1>
        <p className="subtitle">
          Add tasks, complete them, and remove them when finished.
        </p>

        <div className="inputRow">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                addTask();
              }
            }}
            placeholder="Add a new task..."
          />

          <button onClick={addTask}>Add Task</button>
        </div>

        {tasks.length === 0 ? (
          <p className="emptyState">No tasks yet. Add your first task above.</p>
        ) : (
          <ul className="taskList">
            {tasks.map((task) => (
              <li key={task.id} className={task.completed ? "completed" : ""}>
                <label>
                  <input
                    type="checkbox"
                    checked={task.completed}
                    onChange={() => toggleTask(task.id)}
                  />

                  <span>{task.title}</span>
                </label>

                <button className="deleteButton" onClick={() => deleteTask(task.id)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default App;
""",
        ),
        GeneratedFile(
            path="src/App.css",
            content="""* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #020617;
  color: #e5e7eb;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button,
input {
  font: inherit;
}

.app {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
}

.card {
  width: min(720px, 100%);
  border: 1px solid #1e293b;
  border-radius: 24px;
  background: #0f172a;
  padding: 32px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}

.eyebrow {
  margin: 0 0 12px;
  color: #38bdf8;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 48px;
  letter-spacing: -0.05em;
}

.subtitle {
  color: #94a3b8;
  line-height: 1.6;
}

.inputRow {
  display: flex;
  gap: 12px;
  margin: 28px 0;
}

.inputRow input {
  flex: 1;
  border: 1px solid #334155;
  border-radius: 14px;
  background: #020617;
  color: #f8fafc;
  padding: 14px 16px;
  outline: none;
}

.inputRow input:focus {
  border-color: #38bdf8;
}

button {
  border: 0;
  border-radius: 14px;
  background: #38bdf8;
  color: #020617;
  padding: 12px 16px;
  font-weight: 900;
  cursor: pointer;
}

.taskList {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.taskList li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid #1e293b;
  border-radius: 16px;
  background: #020617;
  padding: 14px;
}

.taskList label {
  display: flex;
  align-items: center;
  gap: 10px;
}

.taskList li.completed span {
  color: #64748b;
  text-decoration: line-through;
}

.deleteButton {
  background: #ef4444;
  color: white;
}

.emptyState {
  border: 1px dashed #334155;
  border-radius: 16px;
  color: #64748b;
  padding: 24px;
  text-align: center;
}
""",
        ),
    ]