import { useState } from "react";

type TaskState = "idle" | "submitted" | "approval_required" | "failed";

export function App() {
  const [task, setTask] = useState("");
  const [capability, setCapability] = useState("filesystem.read");
  const [operation, setOperation] = useState("filesystem.read_file");
  const [tool, setTool] = useState("read_file");
  const [scope, setScope] = useState("D:/workspace");
  const [state, setState] = useState<TaskState>("idle");
  const submit = async () => {
    if (!task.trim()) return;
    const response = await fetch("/api/tasks", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({task_id: crypto.randomUUID(), principal_id: "user:console", title: task, resource_scope: scope, steps: [{step_id: "step-1", capability_id: capability, operation_id: operation, tool_name: tool, risk_level: "low"}]})});
    setState(response.ok ? "submitted" : response.status === 403 ? "approval_required" : "failed");
  };
  return <main><h1>AURA Console</h1><label>Task<input value={task} onChange={(event) => setTask(event.target.value)} /></label><label>Capability<input value={capability} onChange={(event) => setCapability(event.target.value)} /></label><label>Operation<input value={operation} onChange={(event) => setOperation(event.target.value)} /></label><label>Tool<input value={tool} onChange={(event) => setTool(event.target.value)} /></label><label>Scope<input value={scope} onChange={(event) => setScope(event.target.value)} /></label><button onClick={submit}>Plan and execute</button><p aria-live="polite">Status: {state}</p><p>All actions require server-side capability authorization.</p></main>;
}
