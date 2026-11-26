import AstralCore from "./components/AstralCore";
import SystemDrawer from "./components/SystemDrawer";
import "./astral-hud.css";
import DynamicHologram3D from "./components/DynamicHologram3D";
import CapabilityWorkbench from "./components/CapabilityWorkbench";
import CapabilityAndToolCenter from "./components/CapabilityAndToolCenter";
import ChatTranscript, { type ChatTurn } from "./components/ChatTranscript";
import EvolutionReviewPanel from "./components/EvolutionReviewPanel";
import StageCControlPanel from "./components/StageCControlPanel";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  AuraApiError,
  createTask,
  generateTaskPlan,
  getHealth,
  getTask,
  getUIContract,
  runSelfDiscovery,
  getContinuousEvolutionStatus, setContinuousEvolution,
  type ContinuousEvolutionStatus,
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

function durumMetni(value: string): string {
  const labels: Record<string, string> = {
    ok: "tamam",
    healthy: "sağlıklı",
    ready: "hazır",
    running: "çalışıyor",
    connected: "bağlı",
    configured: "yapılandırıldı",
    unknown: "bilinmiyor",
    not_configured: "yapılandırılmadı",
    disabled: "devre dışı",
    stopped: "durduruldu",
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
function ContinuousEvolutionQuickControl() {
  const [status, setStatus] = useState<ContinuousEvolutionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      void getContinuousEvolutionStatus().then(result => {
        if (mounted) setStatus(result);
      }).catch(() => { if (mounted) setStatus(null); });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);
  const toggle = async () => {
    if (!status || busy) return;
    setBusy(true);
    try {
      setStatus(await setContinuousEvolution(status.state !== "RUNNING"));
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sürekli mod kullanılamıyor");
    } finally {
      setBusy(false);
    }
  };
  return <div className="flex items-center gap-2">
    <button type="button"
      aria-label="Kendini Geliştirme: sürekli MCP yetenek keşfini aç veya kapat"
      aria-pressed={status?.state === "RUNNING"}
      disabled={busy || !status}
      title={error || "Sürekli MCP keşfi; yeni yetenekler Owner izni ve bağımsız attestasyon gerektirir"}
      onClick={() => void toggle()}
      className={"rounded border px-3 py-2 text-[9px] disabled:opacity-50 " +
        (status?.state === "RUNNING" ? "border-cyan-400 text-cyan-200" :
         "border-cyan-950 text-slate-400")}>
      <span className={status?.state === "RUNNING" ? "animate-pulse" : ""}>
        {status?.state === "RUNNING" ? "● " : "○ "}
      </span>
      KENDİNİ GELİŞTİRME
    </button>
    {status && <span role="status" className="text-[9px] tracking-normal text-cyan-400">
      {status.scanned_candidates} taranan · {status.queued_packages} kuyrukta · {status.active_count} aktif
    </span>}
    {error && <span role="alert" className="max-w-36 truncate text-amber-300" title={error}>
      İŞLEM BAŞARISIZ
    </span>}
  </div>;
}

export default function App() {
  const [mainView, setMainView] = useState<"capabilities" | "hud">("hud");
  const [drawer, setDrawer] = useState(false);
  const closeDrawer = useCallback(() => setDrawer(false), []);
  const [speechEnabled, setSpeechEnabled] = useState(true);
  const [llmOffline, setLlmOffline] = useState(false);
  const [audioEnergy, setAudioEnergy] = useState(0);
  const [micEnergy, setMicEnergy] = useState(0);
  const executionRef = useRef(false);
  const [chatHistory, setChatHistory] = useState<ChatTurn[]>([]);
  const [assistantHistory, setAssistantHistory] = useState<Array<{role: "user" | "assistant"; content: string}>>([]);
  const activeReplyId = useRef<string | null>(null);
  const handleAssistantDelta = useCallback((delta: string) => {
    setChatHistory((current) => current.map((turn) =>
      turn.id === activeReplyId.current ? { ...turn, content: turn.content + delta } : turn
    ));
  }, []);
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
    useState<string[]>([]);

  const voice = useAuraVoice((directive) => {
    setCommand(directive);
    setError(null);
    setSessionState("idle");
    pushTelemetry("SES METNİ HAZIR — ÇALIŞTIRMAK İÇİN ENTER GEREKLİ");
  });

  const continuousVoice = useContinuousAuraVoice((directive) => {
    setCommand(directive);
    setError(null);
    setSessionState("idle");
    pushTelemetry("SÜREKLİ DİNLEMEDEN KONUŞMA METNİ HAZIR — ENTER ONAYI GEREKLİ");
  });

  const fullDuplex = useFullDuplexAura(
    (directive) => {
      setCommand(directive);
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
    degraded?: boolean,
  ) => {
    if (status === "error") setLlmOffline(Boolean(degraded));
    if (status === "ready" || status === "speaking") setLlmOffline(false);
    setSessionState(status === "ready" ? "idle" : status);
    if (status === "ready") {
      setSystemState("idle");
      setTaskState("HAZIR");
      setError(null);
      pushTelemetry("ASİSTAN YANITI TAMAMLANDI · HAZIR");
    }
    if (status === "error") {
      setChatHistory((current) => current.map((turn) =>
        turn.id === activeReplyId.current && !turn.content
          ? { ...turn, content: errorMessage ?? "Yerel model yanıtı alınamadı." }
          : turn
      ));
      // A successful task can still fail while generating or playing its answer.
      // Keep the task summary and lifecycle state consistent with that failure.
      setTaskState("ERROR");
      setSystemState("idle");
      setSessionState("error");
      setError(errorMessage ?? "Sesli yanıt tamamlanamadı. Hata ayrıntılarını inceleyip yeniden deneyin.");
      pushTelemetry("ASİSTAN YANITI BAŞARISIZ");
    }
  }, []);

  useEffect(() => {
    const update = (event: Event) => setAudioEnergy(Number((event as CustomEvent<number>).detail) || 0);
    window.addEventListener("aura:audio-energy", update);
    return () => window.removeEventListener("aura:audio-energy", update);
  }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setMicEnergy(Math.max(continuousVoice.amplitudeRef.current, fullDuplex.amplitudeRef.current)), 70);
    return () => clearInterval(timer);
  }, [continuousVoice.amplitudeRef, fullDuplex.amplitudeRef]);
  const captureSessionState = captureToSessionState(voice.state);
  const visibleSessionState =
    captureSessionState === "listening" ||
    (captureSessionState === "processing" && sessionState === "idle") ||
    (captureSessionState === "error" && sessionState === "idle")
      ? captureSessionState
      : fullDuplex.speaking ? "speaking" : (continuousVoice.active || fullDuplex.active) && sessionState === "idle" ? "listening" : sessionState;

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

    if (!text || executionRef.current || sessionBusy || systemState !== "idle") return;
    executionRef.current = true;
    setHologramTarget("");
    setAssistantHistory(chatHistory.filter((turn) =>
      (turn.role === "user" || turn.role === "assistant") && turn.content.trim()
    ).slice(-8).map((turn) => ({ role: turn.role as "user" | "assistant", content: turn.content.slice(0, 4000) })));
    setChatHistory((current) => [...current, { id: makeId(), role: "user" as const, content: text }].slice(-40));
    setError(null);
    setSessionState("processing");
    setSystemState("thinking");
    setTaskState("PLANLANIYOR");

    pushTelemetry(
      `DİREKTİF ALINDI: ${text}`,
    );

    try {
      let generated = await generateTaskPlan(text);
      let projection: { target: string; model: VisualizationModelId } | null = null;

      if (generated.resource_scope === "local-discovery" && generated.steps.length === 0) {
        setTaskId(null);
        setPlan([]);
        setResearchOutput(null);
        setSystemState("executing");
        setTaskState("GITHUB KEŞFİ");
        try {
          const found = await runSelfDiscovery();
          const descriptions = found.items.slice(0, 9).map((item) => [
            "**" + item.repository + "** · ⭐ " +
              (typeof item.stars === "number" ? item.stars : "bilinmiyor") +
              " · Lisans: " + item.license,
            item.description,
            "AURA'ya katkısı: " + item.capability_hint,
            item.url,
            "Paket: " + (item.package_status ?? "Staging bekleniyor") +
              (item.package_error ? " — " + item.package_error : ""),
            "Durum: Owner Control Plane inceleme kuyruğunda (aktivasyon yapılmadı).",
          ].join("\n"));
          const stagingFailures = (found.staging_rejected ?? []).map((failure) =>
            "⚠ Staging reddedildi: " + failure.repository + " — " + failure.reason
          );
          const warnings = (found.failed_queries ?? []).map((failure) =>
            "⚠ GitHub sorgusu başarısız: " + failure.query +
            " — " + failure.reason
          );
          const reply = [
            found.partial
              ? "SelfDiscoveryEngine GitHub taraması kısmen tamamlandı; başarılı sorguların gerçek sonuçları kaydedildi."
              : "SelfDiscoveryEngine gerçek GitHub Public Search taramasını tamamladı.",
            "Yeni öneri: " + (found.new_count ?? 0) +
              " · Kalıcı öneri kuyruğu: " + found.proposal_count,
            "Staging denemesi: " + (found.staging_attempted ?? 0) +
              " · İndirilen: " + (found.staged_count ?? 0) +
              " · Statik doğrulanan: " + (found.verified_count ?? 0) +
              " · Toplam hazır paket: " + (found.static_ready_count ?? 0),
            ...stagingFailures,
            ...warnings,
            ...descriptions,
            descriptions.length === 0
              ? "Bu canlı taramada lisans ve yerel çalışabilirlik filtresini geçen repo bulunamadı."
              : "Repo kayıtları GitHub metadata/README kanıtıdır; güvenli staging kaynak arşivi indirebilir ancak kod çalıştırılmadı.",
            "Bağımsız Owner Control Plane ve sandbox incelemesi olmadan entegrasyon yapılmaz.",
          ].join("\n\n");
          setChatHistory((current) => [...current, {
            id: makeId(), role: "assistant" as const,
            content: reply, source: "SelfDiscoveryEngine · GitHub Keşif",
            reviewAvailable: true,
          }].slice(-40));
          setResearchOutput(found);
          const replyId = makeId();
          activeReplyId.current = replyId;
          setChatHistory(current => [...current, { id: replyId, role: "assistant" as const, content: "", source: "Ollama · keşif özeti" }].slice(-40));
          setAssistantDirective("Keşif sonuçlarını doğal Türkçe ile özetle; ham bağlantıları okuma.");
          setAssistantRequestId(current => current + 1);
          setTaskState("HAZIR");
          pushTelemetry(found.partial
            ? "GITHUB TARAMASI KISMİ BAŞARILI · SORGULAR: " + (found.successful_queries ?? 0)
            : "GERÇEK GITHUB REPO TARAMASI TAMAMLANDI");
        } catch (cause) {
          const reason = cause instanceof Error ? cause.message
            : "GitHub keşif hizmeti yanıt vermedi.";
          setChatHistory((current) => [...current, {
            id: makeId(), role: "assistant" as const,
            content: "Canlı GitHub keşfi başarısız: " + reason,
            source: "SelfDiscoveryEngine · GitHub Keşif",
          }].slice(-40));
          setTaskState("BAŞARISIZ");
          setError(reason);
          pushTelemetry("GITHUB KEŞFİ BAŞARISIZ: " + reason);
        } finally {
          setSystemState("idle");
          setSessionState("idle");
        }
        return;
      }

      if (generated.resource_scope === "local-assistant" &&
          generated.steps.length === 0) {
        // A conversation is not an agent task: no task creation, no MCP
        // permissions, no automatic computer/browser action.
        setPlan([]);
        setTaskId(null);
        setResearchOutput(null);
        const replyId = makeId();
        activeReplyId.current = replyId;
        setChatHistory((current) => [...current, { id: replyId, role: "assistant" as const, content: "", source: "Ollama · yerel model" }].slice(-40));
        setAssistantDirective(text.replace(/^aura(?:[\s,:;.!?-]+|$)/i, "").trim() || text);
        setAssistantRequestId((current) => current + 1);
        setSystemState("idle");
        setTaskState("YANIT ÜRETİLİYOR");
        pushTelemetry("YEREL ASİSTAN: STREAMING YANIT BAŞLATILDI");
        return;
      }

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

        projection = {
          target: typeof rawTarget === "string" && rawTarget.trim() ? rawTarget.trim().slice(0, 120) : "AURA yordamlı modeli",
          model: modelId as VisualizationModelId,
        };
        // The deterministic visualization service is presentation-only. For
        // an external object obtain a real governed research plan first.
        if (/matris|matrix/i.test(text)) {
          setHologramTarget(projection.target);
          setHologramModelId(projection.model);
          setResearchOutput({ presentation: "illustrative procedural model", health });
          setPlan(generated.steps);
          setTaskId(null);
          const replyId = makeId();
          activeReplyId.current = replyId;
          setChatHistory(current => [...current, { id: replyId, role: "assistant" as const, content: "", source: "Core · yordamlı matris" }].slice(-40));
          setAssistantDirective("AURA çekirdek durumunu mevcut bağlama göre açıkla ve bir takip sorusu sor.");
          setAssistantRequestId(current => current + 1);
          setSystemState("idle");
          return;
        }
        const subject = projection.target.replace(/\b(?:göster|goster|çiz|ciz|yansıt|yansit|visualize|draw|create|make|3b|3d)\b/gi, "").trim();
        generated = await generateTaskPlan("Araştır: " + subject);
        if (!generated.steps.length || generated.steps.some(step => step.capability_id !== "internet.search")) {
          throw new Error("Görselleştirme için doğrulanmış araştırma planı oluşturulamadı.");
        }

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

      const submittedId = makeId();
      setTaskId(submittedId);
      const submitted = await createTask({
        task_id: submittedId,
        principal_id: "local_owner",
        title: text,
        resource_scope:
          generated.resource_scope ||
          "local_default",
        steps: generated.steps,
      });

      // Read authoritative persisted task state; events are observation only.
      const result = await getTask(submitted.task_id);
      setTaskId(result.task_id);
      setTaskState(durumMetni(result.state).toLocaleUpperCase("tr-TR"));
      const nextSessionState = operationToSessionState(result.state);
      setSessionState(nextSessionState);

      pushTelemetry(
        `GÖREV ${result.task_id} → ${result.state.toUpperCase()}`,
      );

      if (result.state === "awaiting_approval" || result.state === "pending_approval") {
        setSystemState("idle");
        setChatHistory((current) => [...current, {
          id: makeId(), role: "assistant" as const,
          content: "Görev beklemeye alındı. Ayrı yetkili Owner incelemesi gerekli.",
          source: generated.steps.map((step) => step.capability_id).join(", "),
          approvalId: result.steps.find((step) => step.approval_id)?.approval_id ?? null,
        }].slice(-40));
        pushTelemetry("YÜRÜTME ENGELLENDİ — AÇIK ONAY GEREKLİ");
        return;
      }

      if (["failed", "cancelled", "timed_out"].includes(result.state)) {
        setSystemState("idle");
        setTaskState("BAŞARISIZ");
        setSessionState("idle");
        // Only server-returned, bounded step error metadata is shown. Never
        // fabricate a completed result or leave a blank assistant bubble.
        const detail = result.steps.find((step) => step.reason)?.reason;
        const reason = typeof detail === "string" ? detail.slice(0, 280) : "Sağlayıcı veya yetki denetimi tamamlanamadı.";
        const message = `Görev ${result.state}: ${reason}`;
        setChatHistory((current) => [...current, {
          id: makeId(), role: "assistant" as const,
          content: message,
          source: generated.steps.map((step) => step.capability_id).join(", "),
        }].slice(-40));
        setError(message);
        pushTelemetry(`GÖREV SONLANDIRILDI: ${result.state.toUpperCase()}`);
        return;
      }

      if (result.state === "succeeded") {
        setSystemState("idle");
        if (projection) {
          setHologramTarget(projection.target);
          setHologramModelId(projection.model);
        }
        setResearchOutput(result.steps);
        const replyId = makeId();
        activeReplyId.current = replyId;
        setChatHistory((current) => [...current, {
          id: replyId, role: "assistant" as const, content: "",
          source: "MCP Gateway · " + generated.steps.map((step) => step.capability_id).join(", "),
        }].slice(-40));
        setAssistantDirective(projection ? text + " — Araştırma sonuçlarına dayanarak açıkla. 3B model temsili ve ölçeksizdir; doğrulanmış CAD ya da termal ölçüm değildir. Kullanıcıya hangi bölümü incelemek istediğini sor." : text);
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
      setChatHistory((current) => [...current, {
        id: makeId(), role: "assistant" as const, content: message, source: "Core hata tanısı",
      }].slice(-40));
      pushTelemetry(`HATA: ${message}`);
    } finally { executionRef.current = false; }
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

  const latestReply = [...chatHistory].reverse().find(turn => turn.role === "assistant");
  const blocked = systemState !== "idle" || sessionBusy;
  const quick = ["Porsche 911'in motorunu göster", "Sistem ve MCP durumunu araştır", "Yeni evrim önerilerini kontrol et", "AURA çekirdek matrisini yansıt"];
  return <>
    <div className="astral-dashboard">
      <header className="astral-top">
        <div className="astral-brand" data-online={isHealthyStatus(coreStatus)}><i /><b>AURA <span style={{color:"#00e7f1"}}>//</span> CORE</b><small>Core: {durumMetni(coreStatus)} · Gateway: {durumMetni(gatewayStatus)}</small></div>
        <div className="astral-actions">
          {llmOffline && <span className="astral-degraded" role="status">LLM OFFLINE / DEGRADED</span>}
          <button type="button" className="astral-pill" aria-pressed={speechEnabled} onClick={() => {
            if (speechEnabled) void fullDuplex.interrupt();
            setSpeechEnabled(value => !value);
          }}>{speechEnabled ? "Ses aktif" : "Ses kapalı"}</button>
          <button type="button" className="astral-pill" onClick={() => setMainView(mainView === "hud" ? "capabilities" : "hud")}>{mainView === "hud" ? "Yetenek merkezi" : "HUD"}</button>
          <button type="button" className="astral-pill" onClick={() => setDrawer(true)}>Sistem Çekirdeği &amp; Evrim{approvals.length ? " · " + approvals.length : ""}</button>
        </div>
      </header>
      {mainView === "capabilities" ? <CapabilityAndToolCenter onInsertDirective={value => { setCommand(value); setMainView("hud"); }} /> :
        <main className="astral-stage">
          <AstralCore state={visibleSessionState} amplitude={Math.max(audioEnergy, micEnergy, voice.amplitude)} docked={!!hologramTarget} />
          {hologramTarget && <div className="astral-projection">
            <DynamicHologram3D target={hologramTarget} modelId={hologramModelId} active={true} />
            <button type="button" className="astral-pill" onClick={() => setHologramTarget("")}>Projeksiyonu kapat</button>
          </div>}
        </main>}
      <footer className="astral-bottom">
        <div className="astral-subtitle" role="status"><small>AURA // HOLOGRAFİK İLETİŞİM</small>{latestReply?.content || (blocked ? sessionStateLabel(visibleSessionState) : "Komutunuzu bekliyorum. Araştırma, 3B projeksiyon veya sistem incelemesi isteyebilirsiniz.")}</div>
        {error && <div role="alert" className="astral-degraded">{error}</div>}
        {visibleSessionState === "awaiting_approval" && <button type="button" className="astral-pill" onClick={() => setDrawer(true)}>Bağımsız Owner onayı gerekiyor · İncele</button>}
        <div className="astral-chips">{quick.map(value => <button type="button" className="astral-pill" key={value} disabled={blocked} onClick={() => { setCommand(value); void executeDirective(value); setCommand(""); }}>{value}</button>)}</div>
        <form className="astral-command" onSubmit={handleSubmit}>
          <button type="button" className="astral-pill" disabled={!voice.available || blocked || fullDuplex.active || continuousVoice.active} onClick={voice.state === "recording" || voice.state === "listening" ? voice.stop : voice.start}>{voice.state === "recording" || voice.state === "listening" ? "Durdur" : "Mikrofon"}</button>
          <input aria-label="AURA komutu" value={command} onChange={event => setCommand(event.target.value)} placeholder="AURA'ya seslenin veya komut yazın…" disabled={blocked} />
          <button type="button" className="astral-pill" aria-pressed={continuousVoice.active} disabled={blocked || fullDuplex.active || voice.state === "recording"} onClick={() => continuousVoice.active ? continuousVoice.stop() : void continuousVoice.start()}>{continuousVoice.active ? "Dinlemeyi kapat" : "Sürekli dinle"}</button>
          <button type="submit" className="astral-pill" disabled={blocked || !command.trim()}>İlet</button>
        </form>
        <div className="astral-status">{sessionStateLabel(visibleSessionState)} · {eventsConnected ? "GÜVENLİ OLAY BAĞLANTISI" : taskState}{continuousVoice.active ? " · " + continuousVoice.message : ""}</div>
      </footer>
      <SystemDrawer open={drawer} onClose={closeDrawer}>
        <section className="astral-card"><h3>CANLI CORE DURUMU</h3>
          <StatusItem label="Çekirdek" value={kernelStatus} /><StatusItem label="Gateway" value={gatewayStatus} /><StatusItem label="PermissionEngine" value={permissionStatus} /><StatusItem label="EventBus" value={eventBusStatus} /><StatusItem label="Öğrenme" value={learningStatus} />
          <p>Görev: {taskState} {taskId && <small>{taskId}</small>}</p><p>Plan: {plan.map(step => step.tool_name).join(" → ") || "Direktif bekleniyor"}</p><p>{sources.length} araştırma olayı · {approvals.length} yetki olayı</p>
          {approvals.map((event, index) => <p key={event.id ?? index}>{event.event ?? event.type}</p>)}
          <a href="http://localhost:8766/" target="_blank" rel="noopener noreferrer">Bağımsız Owner incelemesini aç</a>
          <details><summary>Olay günlüğü</summary>{telemetry.map((line, index) => <p key={index}>{line}</p>)}</details>
        </section>
        <ContinuousEvolutionQuickControl />
        <ChatTranscript turns={chatHistory} />
        <FullDuplexPanel voice={fullDuplex} goal={command} />
        <EvolutionReviewPanel /><StageCControlPanel /><CapabilityWorkbench />
      </SystemDrawer>
    </div>
    <AuraJarvisBridge directive={assistantDirective} researchOutput={researchOutput} requestId={assistantRequestId} onStatus={handleVoiceStatus} speakThroughSession={fullDuplex.speak} sessionActive={fullDuplex.active} enableSpeech={speechEnabled} history={assistantHistory} onDelta={handleAssistantDelta} />
  </>;
}
