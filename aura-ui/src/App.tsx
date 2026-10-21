import ArcReactor3D from "./components/ArcReactor3D";
import DynamicHologram3D from "./components/DynamicHologram3D";
import CapabilityWorkbench from "./components/CapabilityWorkbench";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import {
  AuraApiError,
  createTask,
  generateTaskPlan,
  getHealth,
  getUIContract,
  type HealthResponse,
  type TaskStep,
} from "./api/client";
import {
  captureToSessionState,
  operationToSessionState,
  sessionStateLabel,
  type VoiceSessionState,
} from "./voice/sessionState";

import { useAuraVoice } from "./voice/useAuraVoice";
import { useContinuousAuraVoice } from "./voice/useContinuousAuraVoice";
import { useFullDuplexAura } from "./voice/useFullDuplexAura";
import FullDuplexPanel from "./FullDuplexPanel";
import AuraJarvisBridge from "./AuraJarvisBridge";
import { useTaskEvents } from "./hooks/useTaskEvents";

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
  return (
    <ArcReactor3D
      active={active}
      level={level}
      size={320}
    />
  );
}

function durumMetni(value: string): string {
  const labels: Record<string, string> = {
    ok: "tamam",
    healthy: "sağlıklı",
    ready: "hazır",
    running: "çalışıyor",
    connected: "bağlı",
    configured: "yapılandırıldı",
    unknown: "bilinmiyor",
    offline: "çevrimdışı",
    standby: "beklemede",
    queued: "kuyrukta",
    processing: "işleniyor",
    planning: "planlanıyor",
    executing: "yürütülüyor",
    succeeded: "başarılı",
    failed: "başarısız",
    cancelled: "iptal edildi",
    timed_out: "zaman aşımına uğradı",
    awaiting_approval: "onay bekliyor",
    pending_approval: "onay bekliyor",
    error: "hata",
    idle: "boşta",
  };
  return labels[value.toLowerCase()] ?? value;
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






type VisualizationModelId =
  | "procedural-object-v1"
  | "gear-v1"
  | "sphere-v1"
  | "motor-v1";
export default function App() {
  const [researchOutput, setResearchOutput] =
    useState<unknown>(null);

  const [assistantDirective, setAssistantDirective] =
    useState("");

  const [assistantRequestId, setAssistantRequestId] =
    useState(0);

  const [command, setCommand] = useState("");
  const [hologramTarget, setHologramTarget] = useState("");
  const [hologramModelId, setHologramModelId] =
    useState<VisualizationModelId>("procedural-object-v1");
  const [plan, setPlan] = useState<TaskStep[]>([]);
  const [health, setHealth] =
    useState<HealthResponse | null>(null);

  const [systemState, setSystemState] =
    useState<"idle" | "thinking" | "executing">("idle");

  const [taskState, setTaskState] =
    useState("BEKLEMEDE");

  const [taskId, setTaskId] =
    useState<string | null>(null);

  const [error, setError] =
    useState<string | null>(null);

  const [sessionState, setSessionState] =
    useState<VoiceSessionState>("idle");

  const { events, connected: eventsConnected } =
    useTaskEvents(taskId);

  const liveEvents = events.slice(-8).reverse();
  const sources = liveEvents.filter((event) =>
    /source|research|search/i.test(event.event ?? event.type ?? ""),
  );
  const approvals = liveEvents.filter((event) =>
    /approval|permission|authoriz/i.test(event.event ?? event.type ?? ""),
  );

  const [telemetry, setTelemetry] =
    useState<string[]>([
      "AURA CORE ÇALIŞIYOR",
      "İZİN MOTORU HAZIR",
      "MCP AĞ GEÇİDİ HAZIR",
    ]);

  const voice = useAuraVoice((directive) => {
    setCommand(directive);
    setHologramTarget(directive);
    setError(null);
    setSessionState("idle");
    pushTelemetry("SES METNİ HAZIR — ÇALIŞTIRMAK İÇİN ENTER GEREKLİ");
  });

  const continuousVoice = useContinuousAuraVoice((directive) => {
    setCommand(directive);
    setHologramTarget(directive);
    setError(null);
    setSessionState("idle");
    pushTelemetry("SÜREKLİ DİNLEMEDEN KONUŞMA METNİ HAZIR — ENTER ONAYI GEREKLİ");
  });

  const fullDuplex = useFullDuplexAura(
    (directive) => {
      setCommand(directive);
      setHologramTarget(directive);
      setError(null);
      pushTelemetry("FULL-DUPLEX STT METNİ HAZIR — GÖREV İÇİN ENTER ONAYI GEREKLİ");
    },
    (status) => {
      if (status === "speaking") setSessionState("speaking");
      else if (status === "listening") setSessionState("listening");
      else if (status === "idle") setSessionState("idle");
      else if (status === "error") setSessionState("error");
    },
  );

  const handleVoiceStatus = useCallback((
    status: "processing" | "ready" | "speaking" | "error",
    errorMessage?: string,
  ) => {
    setSessionState(status === "ready" ? "idle" : status);
    if (status === "error") {
      // A successful task can still fail while generating or playing its answer.
      // Keep the task summary and lifecycle state consistent with that failure.
      setTaskState("ERROR");
      setSessionState("error");
      setError(errorMessage ?? "Sesli yanıt tamamlanamadı. Hata ayrıntılarını inceleyip yeniden deneyin.");
      pushTelemetry("ASİSTAN YANITI BAŞARISIZ");
    }
  }, []);

  const captureSessionState = captureToSessionState(voice.state);
  const visibleSessionState =
    captureSessionState === "listening" ||
    (captureSessionState === "processing" && sessionState === "idle") ||
    (captureSessionState === "error" && sessionState === "idle")
      ? captureSessionState
      : sessionState;

  const sessionBusy =
    visibleSessionState === "processing" ||
    visibleSessionState === "responding" ||
    visibleSessionState === "speaking" ||
    visibleSessionState === "awaiting_approval";

  useEffect(() => {
    if (systemState !== "idle" || sessionBusy) {
      continuousVoice.stop();
    }
  }, [systemState, sessionBusy, continuousVoice.stop]);

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

    void getUIContract().then((contract) => {
      if (mounted) {
        setTelemetry((current) => [
          `ARAYÜZ SÖZLEŞMESİ v${contract.contract_version} HAZIR`,
          ...current,
        ].slice(0, 8));
      }
    }).catch((cause: unknown) => {
      if (mounted) {
        const message = cause instanceof AuraApiError
          ? `${cause.message}${cause.requestId ? ` (istek kimliği: ${cause.requestId})` : ""}`
          : "Arayüz-Core sözleşmesi alınamadı.";
        setError(message);
        setSessionState("error");
      }
    });

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
    setSessionState("processing");
    setSystemState("thinking");
    setTaskState("PLANLANIYOR");

    pushTelemetry(
      `DİREKTİF ALINDI: ${text}`,
    );

    try {
      const generated = await generateTaskPlan(text);

      const visualizationStep = generated.steps.find(
        (step) => step.capability_id === "3d.visualize"
      );

      if (visualizationStep) {
        const args = visualizationStep.arguments as Record<string, unknown>;
        const allowedModelIds: readonly VisualizationModelId[] = [
          "procedural-object-v1",
          "gear-v1",
          "sphere-v1",
          "motor-v1",
        ];

        const modelId = args?.model_id;
        const rawTarget = args?.target;

        if (
          typeof modelId !== "string" ||
          !allowedModelIds.some((allowed) => allowed === modelId)
        ) {
          throw new Error("Desteklenmeyen görselleştirme modeli kimliği.");
        }

        setError(null);
        setPlan(generated.steps);
        setHologramTarget(
          typeof rawTarget === "string" && rawTarget.trim()
            ? rawTarget.trim().slice(0, 120)
            : "AURA yordamlı modeli"
        );
        setHologramModelId(modelId as VisualizationModelId);
        setTaskId(null);
        setSystemState("idle");
        setTaskState("GÖRSELLEŞTİRME HAZIR");
        pushTelemetry(`CORE PLANI: 3B GÖRSELLEŞTİRME (${modelId})`);
        return;
      }

      if (
        !generated.steps ||
        generated.steps.length === 0
      ) {
        throw new Error(
          "AURA boş bir yürütme planı oluşturdu.",
        );
      }

      setPlan(generated.steps);

      pushTelemetry(
        `PLAN OLUŞTURULDU: ${generated.steps.length} ADIM`,
      );

      setSystemState("executing");
      setTaskState("YÜRÜTÜLÜYOR");

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
      setTaskState(durumMetni(result.state).toLocaleUpperCase("tr-TR"));
      const nextSessionState = operationToSessionState(result.state);
      setSessionState(nextSessionState);

      pushTelemetry(
        `GÖREV ${result.task_id} → ${result.state.toUpperCase()}`,
      );

      if (result.state === "awaiting_approval" || result.state === "pending_approval") {
        setSystemState("idle");
        pushTelemetry("YÜRÜTME ENGELLENDİ — AÇIK ONAY GEREKLİ");
        return;
      }

      if (["failed", "cancelled", "timed_out"].includes(result.state)) {
        setSystemState("idle");
        setError(`Görev durumu: ${result.state}. Arayüz başka bir eylem yürütmedi.`);
        pushTelemetry(`GÖREV SONLANDIRILDI: ${result.state.toUpperCase()}`);
        return;
      }

      if (result.state === "succeeded") {
        setSystemState("idle");

        setResearchOutput(result.steps);
        setAssistantDirective(text);
        setAssistantRequestId(
          (current) => current + 1,
        );

        pushTelemetry("YÜRÜTME TAMAMLANDI");
      }
    } catch (cause) {
      setSystemState("idle");
      setTaskState("BAŞARISIZ");
      setSessionState("error");

      const message = cause instanceof AuraApiError
        ? `[${cause.code}] ${cause.message}${cause.requestId ? ` (request: ${cause.requestId})` : ""}`
        : cause instanceof Error
          ? cause.message
          : "AURA yürütmesi başarısız oldu.";

      setError(message);
      pushTelemetry(`HATA: ${message}`);
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

  const kernelStatus =
    health?.components?.kernel?.status ?? "unknown";
  const eventBusStatus =
    health?.components?.event_bus?.status ?? "unknown";
  const learningStatus =
    health?.components?.learning?.status ?? "unknown";

  const isHealthyStatus = (status: string | undefined) =>
    ["ok", "healthy", "ready", "running"].includes(
      (status ?? "").toLowerCase()
    );

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
              ÖZERK ZEKA SİSTEMİ
            </div>
          </div>

          <div className="flex items-center gap-3 text-[9px] tracking-[.18em]">
            <span
              className={[
                "h-1.5 w-1.5 rounded-full",
                isHealthyStatus(coreStatus)
                  ? "bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,.9)]"
                  : "bg-amber-400",
              ].join(" ")}
            />
            CORE {durumMetni(coreStatus).toLocaleUpperCase("tr-TR")}
          </div>
        </header>

        <main className="grid flex-1 grid-cols-1 items-center gap-8 py-8 lg:grid-cols-[230px_minmax(400px,1fr)_270px]">

          <aside className="order-2 lg:order-1">
            <div className="mb-5 text-[9px] font-bold tracking-[.25em] text-cyan-600">
              CORE SİSTEMLERİ
            </div>

            <StatusItem
              label="ÇEKİRDEK"
              value={kernelStatus}
            />

            <StatusItem
              label="AĞ GEÇİDİ"
              value={gatewayStatus}
            />

            <StatusItem
              label="İZİN YÖNETİMİ"
              value={permissionStatus}
            />

            <StatusItem
              label="OLAY VERİ YOLU"
              value={eventBusStatus}
            />

            <StatusItem
              label="ÖĞRENME"
              value={learningStatus}
            />

            <div className="mt-8 rounded border border-cyan-950/70 bg-slate-950/40 p-4">
              <div className="text-[8px] tracking-[.2em] text-slate-600">
                GÜNCEL DURUM
              </div>

              <div className="mt-2 text-lg font-light tracking-[.16em] text-cyan-300">
                {durumMetni(taskState).toLocaleUpperCase("tr-TR")}
              </div>

              <div className={`mt-2 text-[9px] tracking-[.12em] ${
                visibleSessionState === "error" ? "text-red-300" :
                visibleSessionState === "awaiting_approval" ? "text-amber-300" :
                "text-cyan-500"
              }`}>
                {sessionStateLabel(visibleSessionState)}
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
              {hologramTarget.trim() ? (
                <DynamicHologram3D
                  target={hologramTarget}
              modelId={hologramModelId}
                  active={systemState !== "idle" || sessionBusy}
                />
              ) : (
                <ArcReactor
                  active={systemState !== "idle" || sessionBusy}
                  level={sessionBusy ? "executing" : systemState}
                />
              )}

              <div className="absolute -bottom-7 left-1/2 -translate-x-1/2 whitespace-nowrap text-[8px] tracking-[.35em] text-cyan-700">
                {sessionStateLabel(visibleSessionState)}
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

            {visibleSessionState === "awaiting_approval" && (
              <div role="status" className="mt-4 max-w-xl rounded border border-amber-700/70 bg-amber-950/20 px-4 py-3 text-center text-[10px] leading-5 text-amber-200">
                AURA Core açık yetkilendirme bekliyor. Arayüz eylemi kendiliğinden çalıştırmaz veya yeniden denemez.
              </div>
            )}
          </section>

          <aside className="order-3">
            <div className="mb-5 text-[9px] font-bold tracking-[.25em] text-cyan-600">
              SİSTEM GÖZLEMİ
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

            <div className="mt-6 grid gap-3 text-[9px]">
              {[
                ["PLAN", plan.map((step) => step.tool_name).join(" → ") || "Direktif bekleniyor"],
                ["ŞİMDİ ÇALIŞAN", durumMetni(liveEvents[0]?.event ?? liveEvents[0]?.type ?? taskState)],
                ["KAYNAKLAR", sources.length ? `${sources.length} araştırma olayı` : "Henüz kaynak yok"],
                ["İZİN / ONAY", approvals.length ? `${approvals.length} olay` : "Bekleyen onay yok"],
              ].map(([label, value]) => (
                <div key={label} className="rounded border border-cyan-950/70 bg-slate-950/40 p-3">
                  <div className="text-[8px] tracking-[.2em] text-slate-600">{label}</div>
                  <div className="mt-1 break-words font-mono text-[9px] text-cyan-200">{value}</div>
                </div>
              ))}
              <div className="text-[8px] tracking-[.16em] text-slate-600">
                OLAY BAĞLANTISI: {eventsConnected ? "GÜVENLİ / BAĞLI" : "GÖREV BEKLENİYOR"}
              </div>
            </div>
          </aside>
        </main>

        <FullDuplexPanel voice={fullDuplex} />

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
                setHologramTarget(event.target.value);
                setError(null);
              }}
              placeholder="Bir direktif ver..."
              disabled={systemState !== "idle" || sessionBusy}
              className="min-w-0 flex-1 border-b border-cyan-900/70 bg-transparent px-1 py-3 font-mono text-sm text-cyan-100 outline-none placeholder:text-slate-700 focus:border-cyan-400 disabled:opacity-40"
            />

            <button
              type="button"
              disabled={!voice.available || systemState !== "idle" || sessionBusy}
              onClick={
                voice.state === "recording" || voice.state === "listening"
                  ? voice.stop
                  : voice.start
              }
              className="px-3 py-2 text-[9px] tracking-[.18em] text-cyan-500 transition hover:text-cyan-200 disabled:opacity-30"
            >
              {voice.state === "recording" || voice.state === "listening"
                ? "DURDUR"
                : voice.state === "transcribing"
                  ? "SES ÇÖZÜMLENİYOR…"
                  : "SES"}
            </button>

            <button
              type="button"
              disabled={systemState !== "idle" || sessionBusy || voice.state === "recording" || voice.state === "transcribing"}
              onClick={() => continuousVoice.active ? continuousVoice.stop() : void continuousVoice.start()}
              title="Mikrofon erişimi sürekli açık kalır; konuşma metni otomatik çalıştırılmaz."
              aria-pressed={continuousVoice.active}
              className={[
                "border px-3 py-2 text-[9px] tracking-[.12em] transition disabled:opacity-30",
                continuousVoice.active ? "border-amber-400 text-amber-300" : "border-cyan-900/70 text-cyan-700 hover:text-cyan-200",
              ].join(" ")}
            >
              {continuousVoice.active ? "DİNLEMEYİ KAPAT" : "SÜREKLİ DİNLE"}
            </button>

            <button
              type="submit"
              disabled={
                !command.trim() ||
                systemState !== "idle" ||
                sessionBusy
              }
              className="border border-cyan-700/80 px-5 py-2 text-[9px] font-bold tracking-[.2em] text-cyan-300 transition hover:border-cyan-300 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-30"
            >
              ENTER
            </button>
          </form>
          <div className="mx-auto mt-2 max-w-4xl text-center text-[8px] tracking-[.12em] text-slate-500">
            {continuousVoice.active ? continuousVoice.message : voice.message}
          </div>
        </footer>

      </div>
    </div>
      </>
      </>


      <CapabilityWorkbench />
      <AuraJarvisBridge
        directive={assistantDirective}
        researchOutput={researchOutput}
        requestId={assistantRequestId}
        onStatus={handleVoiceStatus}
        speakThroughSession={fullDuplex.speak}
      />
    </>
);
}
