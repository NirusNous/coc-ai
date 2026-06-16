import { useState } from "react";

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
