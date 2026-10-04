import { useState } from "react";
import type { FormEvent } from "react";

import {
  createTask,
  type TaskResponse,
} from "../api/client";

import { useTaskEvents } from "../hooks/useTaskEvents";

function createTaskId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  return `task-${Date.now()}-${Math.random()
    .toString(16)
    .slice(2)}`;
}

export function TaskConsole() {
  const [goal, setGoal] = useState("");
  const [taskId, setTaskId] =
    useState<string | null>(null);

  const [task, setTask] =
    useState<TaskResponse | null>(null);

  const [submitting, setSubmitting] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const {
    events,
    connected,
    reconnecting,
  } = useTaskEvents(taskId);

  async function submit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const trimmedGoal = goal.trim();

    if (!trimmedGoal || submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      /*
       * AURA Core currently requires an explicit TaskRequest.
       *
       * Natural-language planning is intentionally NOT faked here.
       * The planner layer will eventually transform the user's goal
       * into validated PlanSteps.
       *
       * For now we create a deterministic task shell with zero steps.
       * This keeps the UI/API contract correct without bypassing
       * CapabilityRegistry, PermissionEngine or MCPGateway.
       */
      const taskIdValue = createTaskId();

      const response = await createTask({
        task_id: taskIdValue,
        principal_id: "agent:web",
        title: trimmedGoal,
        resource_scope:
          import.meta.env.VITE_RESOURCE_SCOPE ??
          "D:/AURA/workspace",
        steps: [],
      });

      setTaskId(response.task_id);
      setTask(response);
      setGoal("");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "AURA task olusturulamadi.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const state =
    task?.state ??
    "STANDBY";

  return (
    <section className="w-full max-w-4xl">
      <div className="mb-5 flex items-center justify-between border-b border-cyan-900/60 pb-4">
        <div>
          <h2 className="text-xl font-bold tracking-[0.18em] text-cyan-300">
            COMMAND CONSOLE
          </h2>

          <p className="mt-1 text-[10px] tracking-[0.16em] text-cyan-700">
            AURA // DETERMINISTIC EXECUTION
          </p>
        </div>

        <div className="text-right">
          <div className="text-[9px] tracking-[0.16em] text-slate-600">
            EVENT LINK
          </div>

          <div
            className={
              connected
                ? "text-xs text-cyan-300"
                : reconnecting
                  ? "text-xs text-amber-300"
                  : "text-xs text-slate-500"
            }
          >
            {connected
              ? "CONNECTED"
              : reconnecting
                ? "RECONNECTING"
                : "STANDBY"}
          </div>
        </div>
      </div>

      <form
        onSubmit={submit}
        className="rounded-xl border border-cyan-900/60 bg-slate-950/80 p-5 shadow-[0_0_35px_rgba(6,182,212,.05)]"
      >
        <label
          htmlFor="aura-command"
          className="mb-2 block text-[10px] font-bold tracking-[0.2em] text-cyan-500"
        >
          J.A.R.V.I.S. DIRECTIVE
        </label>

        <textarea
          id="aura-command"
          value={goal}
          onChange={(event) =>
            setGoal(event.target.value)
          }
          disabled={submitting}
          rows={6}
          placeholder="Efendim, emrinizdeyim..."
          className="w-full resize-none rounded-lg border border-cyan-900 bg-[#020910] p-4 font-mono text-sm text-cyan-100 outline-none transition focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/30"
        />

        {error && (
          <div className="mt-3 rounded-lg border border-red-900/70 bg-red-950/30 p-3 text-xs text-red-300">
            {error}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1 text-[9px] leading-4 text-slate-600">
            <div>
              STATE:{" "}
              <span className="text-cyan-500">
                {state.toUpperCase()}
              </span>
            </div>

            <div>
              TASK:{" "}
              <span className="text-cyan-700">
                {taskId
                  ? taskId.slice(0, 12)
                  : "NONE"}
              </span>
            </div>

            <div>
              EVENTS:{" "}
              <span className="text-cyan-700">
                {events.length}
              </span>
            </div>
          </div>

          <button
            type="submit"
            disabled={
              submitting ||
              !goal.trim()
            }
            className="rounded-lg border border-cyan-400 bg-cyan-950/70 px-6 py-3 text-[10px] font-bold tracking-[0.2em] text-cyan-200 transition hover:bg-cyan-900/70 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting
              ? "PROCESSING..."
              : "EXECUTE DIRECTIVE"}
          </button>
        </div>
      </form>

      {events.length > 0 && (
        <div className="mt-5 rounded-xl border border-cyan-900/50 bg-slate-950/70 p-4">
          <div className="mb-3 text-[10px] font-bold tracking-[0.18em] text-cyan-600">
            LIVE TELEMETRY
          </div>

          <div className="max-h-80 space-y-2 overflow-y-auto">
            {events.map((event, index) => (
              <pre
                key={
                  event.id ??
                  `${event.event ?? event.type ?? "event"}-${index}`
                }
                className="overflow-x-auto rounded border border-slate-900 bg-black/30 p-2 text-[10px] leading-5 text-cyan-100/70"
              >
                {JSON.stringify(
                  event,
                  null,
                  2,
                )}
              </pre>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}