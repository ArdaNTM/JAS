import { useEffect, useState} from "react";
import type { FormEvent } from "react";

import {
  createTask,
  generateTaskPlan,
  getHealth,
  type HealthResponse,
  type TaskStep,
} from "./api/client";

import { useAuraVoice } from "./voice/useAuraVoice";
import AuraJarvisBridge from "./AuraJarvisBridge";

function makeId(): string {
  return crypto.randomUUID?.() ?? `task-${Date.now()}`;
}

function ArcReactor({
  active,
  level,
}: {
  active: boolean;
  level: "idle" | "thinking" | "executing";
}) {
  const speed =
    level === "executing"
      ? "animate-[spin_1.7s_linear_infinite]"
      : level === "thinking"
        ? "animate-[spin_4s_linear_infinite]"
        : "animate-[spin_18s_linear_infinite]";

  return (
    <div
      className={[
        "relative flex h-72 w-72 items-center justify-center",
        active ? "scale-105" : "scale-100",
        "transition-all duration-700",
      ].join(" ")}
    >
      <div
        className={[
          "absolute inset-0 rounded-full border border-cyan-400/20",
          speed,
        ].join(" ")}
      />

      <div
        className={[
          "absolute inset-5 rounded-full border border-cyan-400/25",
          speed,
        ].join(" ")}
      />

      <div className="absolute inset-10 rounded-full border border-dashed border-cyan-300/20" />

      <div
        className={[
          "absolute inset-16 rounded-full border-2 border-cyan-300/70",
          "shadow-[0_0_55px_rgba(34,211,238,.55),inset_0_0_45px_rgba(34,211,238,.18)]",
          active ? "animate-pulse" : "",
        ].join(" ")}
      />

      <div
        className={[
          "relative h-20 w-20 rounded-full bg-cyan-100",
          "shadow-[0_0_30px_rgba(165,243,252,1),0_0_100px_rgba(34,211,238,.75)]",
          active ? "scale-110" : "",
          "transition-all duration-500",
        ].join(" ")}
      />
    </div>
  );
}

function StatusItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const online = [
    "ok",
    "healthy",
    "ready",
    "configured",
    "running",
    "connected",
  ].includes(value.toLowerCase());

  return (
    <div className="flex items-center justify-between border-b border-cyan-950/60 py-2">
      <span className="text-[9px] tracking-[.18em] text-slate-500">
        {label}
      </span>

      <span className="flex items-center gap-2 text-[9px] uppercase tracking-[.12em] text-cyan-300">
        <span
          className={[
            "h-1.5 w-1.5 rounded-full",
            online
              ? "bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,.9)]"
              : "bg-amber-400",
          ].join(" ")}
        />
        {value}
      </span>
    </div>
  );
}
/*  */






export default function App() {
    const [researchOutput] = useState<unknown>(null);

  const [command, setCommand] = useState("");
  const [plan, setPlan] = useState<TaskStep[]>([]);
  const [health, setHealth] =
    useState<HealthResponse | null>(null);

  const [systemState, setSystemState] =
    useState<"idle" | "thinking" | "executing">("idle");

  const [taskState, setTaskState] =
    useState("STANDBY");

  const [taskId, setTaskId] =
    useState<string | null>(null);

  const [error, setError] =
    useState<string | null>(null);

  const [telemetry, setTelemetry] =
    useState<string[]>([
      "AURA CORE ONLINE",
      "PERMISSION ENGINE ARMED",
      "MCP GATEWAY READY",
    ]);

  const voice = useAuraVoice((directive) => {
    setCommand(directive);
    setError(null);
  });

  useEffect(() => {
    let mounted = true;

    const refresh = async () => {
      try {
        const result = await getHealth();

        if (mounted) {
          setHealth(result);
        }
      } catch {
        if (mounted) {
          setHealth(null);
        }
      }
    };

    void refresh();

    const timer = window.setInterval(
      () => void refresh(),
      5000,
    );

    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  function pushTelemetry(message: string) {
    setTelemetry((current) => [
      message,
      ...current,
    ].slice(0, 8));
  }

  async function executeDirective(
    directive: string,
  ) {
    const text = directive.trim();

    if (!text) {
      return;
    }

    setError(null);
    setSystemState("thinking");
    setTaskState("PLANNING");

    pushTelemetry(
      `DIRECTIVE RECEIVED: ${text}`,
    );

    try {
      const generated =
        await generateTaskPlan(text);

      if (
        !generated.steps ||
        generated.steps.length === 0
      ) {
        throw new Error(
          "AURA generated an empty execution plan.",
        );
      }

      setPlan(generated.steps);

      pushTelemetry(
        `PLAN GENERATED: ${generated.steps.length} STEP(S)`,
      );

      setSystemState("executing");
      setTaskState("EXECUTING");

      const result = await createTask({
        task_id: makeId(),
        principal_id: "local-user",
        title: text,
        resource_scope:
          generated.resource_scope ||
          "public-web",
        steps: generated.steps,
      });

      setTaskId(result.task_id);
      setTaskState(
        result.state.toUpperCase(),
      );

      pushTelemetry(
        `TASK ${result.task_id} → ${result.state.toUpperCase()}`,
      );

      if (result.state === "succeeded") {
        setSystemState("idle");
        pushTelemetry("EXECUTION COMPLETE");
      }
    } catch (cause) {
      setSystemState("idle");
      setTaskState("FAILED");

      const message =
        cause instanceof Error
          ? cause.message
          : "AURA execution failed.";

      setError(message);
      pushTelemetry(`ERROR: ${message}`);
    }
  }

  function handleSubmit(
    event: FormEvent<HTMLFormElement>
,
  ) {
    event.preventDefault();

    const text = command.trim();

    if (!text) {
      return;
    }

    void executeDirective(text);
    setCommand("");
  }

  const coreStatus =
    health?.status ?? "offline";

  const gatewayStatus =
    health?.components?.gateway?.status ??
    "unknown";

  const permissionStatus =
    health?.components?.permission_engine?.status ??
    "unknown";

  return (
      <>

      <>

      <>

    <div className="min-h-screen overflow-hidden bg-[#02060b] text-cyan-100">
      <div className="pointer-events-none fixed inset-0 opacity-40">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(8,145,178,.13),transparent_30%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,.018)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,.018)_1px,transparent_1px)] bg-[size:36px_36px]" />
      </div>

      <div className="relative mx-auto flex min-h-screen max-w-[1700px] flex-col px-6 py-5">

        <header className="flex items-center justify-between border-b border-cyan-950/70 pb-4">
          <div>
            <div className="text-xl font-black tracking-[.35em] text-cyan-200">
              A.U.R.A.
            </div>

            <div className="mt-1 text-[8px] tracking-[.3em] text-slate-600">
              AUTONOMOUS INTELLIGENCE SYSTEM
            </div>
          </div>

          <div className="flex items-center gap-3 text-[9px] tracking-[.18em]">
            <span
              className={[
                "h-1.5 w-1.5 rounded-full",
                coreStatus === "ok"
                  ? "bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,.9)]"
                  : "bg-amber-400",
              ].join(" ")}
            />
            CORE {coreStatus.toUpperCase()}
          </div>
        </header>

        <main className="grid flex-1 grid-cols-1 items-center gap-8 py-8 lg:grid-cols-[230px_minmax(400px,1fr)_270px]">

          <aside className="order-2 lg:order-1">
            <div className="mb-5 text-[9px] font-bold tracking-[.25em] text-cyan-600">
              CORE SYSTEMS
            </div>

            <StatusItem
              label="KERNEL"
              value="running"
            />

            <StatusItem
              label="GATEWAY"
              value={gatewayStatus}
            />

            <StatusItem
              label="PERMISSION"
              value={permissionStatus}
            />

            <StatusItem
              label="EVENT BUS"
              value="connected"
            />

            <StatusItem
              label="LEARNING"
              value="running"
            />

            <div className="mt-8 rounded border border-cyan-950/70 bg-slate-950/40 p-4">
              <div className="text-[8px] tracking-[.2em] text-slate-600">
                CURRENT STATE
              </div>

              <div className="mt-2 text-lg font-light tracking-[.16em] text-cyan-300">
                {taskState}
              </div>

              {taskId && (
                <div className="mt-2 truncate font-mono text-[8px] text-slate-600">
                  {taskId}
                </div>
              )}
            </div>
          </aside>

          <section className="order-1 flex flex-col items-center lg:order-2">

            <div className="relative">
              <ArcReactor
                active={systemState !== "idle"}
                level={systemState}
              />

              <div className="absolute -bottom-7 left-1/2 -translate-x-1/2 whitespace-nowrap text-[8px] tracking-[.35em] text-cyan-700">
                {systemState === "idle"
                  ? "STANDBY"
                  : systemState === "thinking"
                    ? "ANALYZING"
                    : "EXECUTING"}
              </div>
            </div>

            <div className="mt-12 flex min-h-10 items-center justify-center gap-2">
              {plan.map((step) => (
                <div
                  key={step.step_id}
                  title={step.tool_name}
                  className="h-1.5 w-8 rounded-full bg-cyan-400/60 shadow-[0_0_8px_rgba(34,211,238,.45)]"
                />
              ))}
            </div>

            {error && (
              <div className="mt-4 max-w-xl rounded border border-red-900/70 bg-red-950/20 px-4 py-2 text-center text-[10px] text-red-300">
                {error}
              </div>
            )}
          </section>

          <aside className="order-3">
            <div className="mb-5 text-[9px] font-bold tracking-[.25em] text-cyan-600">
              TELEMETRY
            </div>

            <div className="space-y-2">
              {telemetry.map(
                (entry, index) => (
                  <div
                    key={`${entry}-${index}`}
                    className="border-l border-cyan-900/70 pl-3 font-mono text-[8px] leading-4 text-slate-500"
                  >
                    <span className="mr-2 text-cyan-800">
                      {String(
                        telemetry.length - index,
                      ).padStart(2, "0")}
                    </span>

                    {entry}
                  </div>
                ),
              )}
            </div>
          </aside>
        </main>

        <footer className="border-t border-cyan-950/70 pt-4">
          <form
            onSubmit={handleSubmit}
            className="mx-auto flex max-w-4xl items-center gap-3"
          >
            <div className="text-[9px] font-bold tracking-[.2em] text-cyan-700">
              AURA
            </div>

            <input
              value={command}
              onChange={(event) => {
                setCommand(event.target.value);
                setError(null);
              }}
              placeholder="Bir direktif ver..."
              disabled={systemState !== "idle"}
              className="min-w-0 flex-1 border-b border-cyan-900/70 bg-transparent px-1 py-3 font-mono text-sm text-cyan-100 outline-none placeholder:text-slate-700 focus:border-cyan-400 disabled:opacity-40"
            />

            <button
              type="button"
              disabled={!voice.available}
              onClick={
                voice.state === "listening"
                  ? voice.stop
                  : voice.start
              }
              className="px-3 py-2 text-[9px] tracking-[.18em] text-cyan-500 transition hover:text-cyan-200 disabled:opacity-30"
            >
              {voice.state === "listening"
                ? "STOP"
                : "VOICE"}
            </button>

            <button
              type="submit"
              disabled={
                !command.trim() ||
                systemState !== "idle"
              }
              className="border border-cyan-700/80 px-5 py-2 text-[9px] font-bold tracking-[.2em] text-cyan-300 transition hover:border-cyan-300 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-30"
            >
              ENTER
            </button>
          </form>
        </footer>

      </div>
    </div>
      </>
      </>

      
      <AuraJarvisBridge
        command={command}
        researchOutput={researchOutput}
      />
    </>
);
}