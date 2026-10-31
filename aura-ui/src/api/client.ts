import type { UIContractResponse, UIErrorEnvelope } from "./contracts";

export interface TaskStep {
  step_id: string;
  capability_id: string;
  operation_id: string;
  tool_name: string;

  risk_level:
    | "minimal"
    | "low"
    | "medium"
    | "high"
    | "critical";

  arguments?: Record<string, unknown>;
  depends_on?: string[];
  max_attempts?: number;
}

export interface TaskRequest {
  task_id: string;
  principal_id: string;
  title: string;
  resource_scope: string;
  steps: TaskStep[];
}

export interface GeneratedPlan {
  resource_scope: string;
  steps: TaskStep[];
}

export interface TaskStepResult {
  step_id: string;
  state: string;
  attempts: number;
  reason: string;
}

export interface TaskResponse {
  task_id: string;
  plan_id: string;
  state: string;
  steps: TaskStepResult[];
}

export interface HealthComponent {
  status: string;
  error?: string;
}

export interface HealthResponse {
  status: string;
  components: Record<string, HealthComponent>;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

function localizeApiMessage(code: string, message: string): string {
  const known: Record<string, string> = {
    stt_dependency_unavailable: "Yerel ses tanıma bağımlılığı bulunamadı. Core Python ortamını ve kurulumunu kontrol edin.",
    stt_model_load_failed: "Ses tanıma modeli yüklenemedi. AURA_STT_MODEL ayarını ve kullanılabilir belleği kontrol edin.",
    stt_transcription_failed: "Ses çözümlenemedi. Kayıt biçimini, ses düzeyini ve Core günlüklerini kontrol edin.",
    stt_internal_error: "Yerel ses tanıma sırasında beklenmeyen bir hata oluştu.",
    validation_error: "İstek doğrulanamadı. Girilen bilgileri kontrol edin.",
    unauthorized: "Bu işlem için kimlik doğrulaması gerekiyor.",
    forbidden: "Bu işlem için izniniz yok.",
    not_found: "İstenen kaynak bulunamadı.",
    conflict: "İşlem mevcut durumla çakışıyor.",
    rate_limited: "Çok fazla istek gönderildi. Biraz bekleyip yeniden deneyin.",
    provider_unavailable: "Yapılandırılmış hizmet şu anda kullanılamıyor.",
    provider_invalid_response: "Hizmet geçersiz bir yanıt döndürdü.",
    internal_error: "Core içinde beklenmeyen bir hata oluştu.",
    http_error: "İstek tamamlanamadı.",
  };
  if (known[code]) return known[code];
  const safeFallbacks: Array<[RegExp, string]> = [
    [/microphone|audio capture/i, "Mikrofon veya ses kaydı hatası oluştu."],
    [/transcrib|speech.to.text/i, "Ses metne dönüştürülemedi."],
    [/model.*initializ|model.*load/i, "Ses tanıma modeli yüklenemedi."],
    [/request validation failed/i, "İstek doğrulanamadı."],
    [/internal server error/i, "Sunucu içinde beklenmeyen bir hata oluştu."],
  ];
  return safeFallbacks.find(([pattern]) => pattern.test(message))?.[1] ?? "İstek başarısız oldu. Ayrıntılar için Core günlüklerini denetleyin.";
}

export class AuraApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(
    message: string,
    status: number,
    code = "http_error",
    retryable = status >= 500,
    requestId: string | null = null,
    details: unknown = null,
  ) {
    super(message);
    this.name = "AuraApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.requestId = requestId;
    this.details = details;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    },
  );

  if (!response.ok) {
    let envelope: Partial<UIErrorEnvelope> = {};
    try {
      envelope = (await response.json()) as Partial<UIErrorEnvelope>;
    } catch {
      // Non-JSON responses still produce a typed HTTP error.
    }

    const apiError = envelope.error;
    const legacyDetail =
      typeof envelope.detail === "string" ? envelope.detail : undefined;
    throw new AuraApiError(
      localizeApiMessage(apiError?.code ?? "http_error", apiError?.message ?? legacyDetail ?? `API request failed: ${response.status}`),
      response.status,
      apiError?.code ?? "http_error",
      apiError?.retryable ?? response.status >= 500,
      apiError?.request_id ?? response.headers.get("X-Request-ID"),
      apiError?.details ?? envelope.detail ?? null,
    );
  }

  return response.json() as Promise<T>;
}

/** Discover supported UI contract features without binding to a model/provider. */
export function getUIContract(): Promise<UIContractResponse> {
  return request<UIContractResponse>("/api/ui/v1/contract");
}

export function generateTaskPlan(
  directive: string,
): Promise<GeneratedPlan> {
  return request<GeneratedPlan>(
    "/api/tasks/plan",
    {
      method: "POST",
      body: JSON.stringify({
        directive,
      }),
    },
  );
}

export function createTask(
  body: TaskRequest,
): Promise<TaskResponse> {
  return request<TaskResponse>(
    "/api/tasks",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function getTask(
  taskId: string,
): Promise<TaskResponse> {
  return request<TaskResponse>(
    `/api/tasks/${encodeURIComponent(taskId)}`,
  );
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>(
    "/api/health",
  );
}

export async function getWebSocketTicket(): Promise<{
  ticket: string;
  expires_at: number;
}> {
  return request<{
    ticket: string;
    expires_at: number;
  }>("/api/ws/ticket", {
    method: "POST",
  });
}
export interface AssistantRespondRequest {
  message: string;
  research_output?: unknown;
}

export interface AssistantRespondResponse {
  assistant_reply: string;
  model: string;
  degraded: boolean;
}

export function respondAsAssistant(
  message: string,
  researchOutput?: unknown,
): Promise<AssistantRespondResponse> {
  return request<AssistantRespondResponse>(
    "/api/assistant/respond",
    {
      method: "POST",
      body: JSON.stringify({
        message,
        research_output: researchOutput ?? null,
      }),
    },
  );
}

/** Incremental local inference; the existing authenticated loopback proxy injects bearer auth. */
export async function streamAssistantResponse(
  message: string,
  researchOutput: unknown,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<{ model: string; finish_reason: string }> {
  const response = await fetch(`${API_BASE}/api/assistant/respond/stream`, {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/x-ndjson", "Content-Type": "application/json" },
    body: JSON.stringify({ message, research_output: researchOutput ?? null }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Local assistant streaming unavailable (HTTP ${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let completed: { model: string; finish_reason: string } | null = null;
  let total = 0;
  const consume = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as {
      delta?: string; done?: boolean; finish_reason?: string; model?: string; error?: string;
    };
    if (event.error) throw new Error("Yerel model yanıt akışı kesildi.");
    if (typeof event.delta === "string") {
      total += event.delta.length;
      if (total > 24000) throw new Error("Yanıt izin verilen uzunluğu aştı.");
      onDelta(event.delta);
    }
    if (event.done) {
      completed = { model: event.model ?? "", finish_reason: event.finish_reason ?? "stop" };
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffered += decoder.decode(value, { stream: !done });
      if (buffered.length > 70000) throw new Error("Model akışı geçersiz boyutta.");
      let newline = buffered.indexOf("\n");
      while (newline !== -1) {
        consume(buffered.slice(0, newline));
        buffered = buffered.slice(newline + 1);
        newline = buffered.indexOf("\n");
      }
      if (done) {
        if (buffered.trim()) consume(buffered);
        break;
      }
    }
    // The NDJSON callback mutates this variable; assert the union here
    // so TypeScript retains the event-driven narrowing.
    const finalEvent = completed as { model: string; finish_reason: string } | null;
    if (!finalEvent) throw new Error("Model yanıtı tamamlanmadan akış kapandı.");
    if (finalEvent.finish_reason === "length") {
      throw new Error("Model yanıtı token sınırında kesildi. AURA_MAX_TOKENS değerini artırın.");
    }
    return finalEvent;
  } finally {
    reader.releaseLock();
  }
}

export function synthesizeLocalSpeech(text: string): Promise<{
  mime_type: string;
  audio_base64: string;
}> {
  return request("/api/speech/synthesize", { method: "POST", body: JSON.stringify({ text }) });
}


export interface SpeechTranscriptionResponse {
  text: string;
  language: string;
}

/** Send microphone audio to AURA's local faster-whisper endpoint. */
export async function transcribeLocalAudio(blob: Blob): Promise<SpeechTranscriptionResponse> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return request<SpeechTranscriptionResponse>("/api/speech/transcribe", {
    method: "POST",
    body: JSON.stringify({
      audio_base64: btoa(binary),
      mime_type: blob.type || "audio/webm",
      language: "tr",
    }),
  });
}

export interface VectorMemoryItem {
  memory_id?: string;
  content?: string;
  relevance_score?: number;
  tags?: string[];
  principal_id?: string;
}

export function writeVectorMemory(body: {
  principal_id: string;
  content: string;
  tags?: string[];
}): Promise<{ memory_id: string; principal_id: string; stored: boolean; trust: string }> {
  return request("/api/memory/vector", { method: "POST", body: JSON.stringify(body) });
}

export function recallVectorMemory(body: {
  principal_id: string;
  query: string;
  limit?: number;
}): Promise<{ items: VectorMemoryItem[]; count: number; trust: string }> {
  return request("/api/memory/vector/recall", { method: "POST", body: JSON.stringify(body) });
}

export function analyzeLocalVision(body: {
  image_base64: string;
  prompt: string;
}): Promise<{ model: string; analysis: string; provider: string; cloud_used: boolean }> {
  return request("/api/vision/analyze", { method: "POST", body: JSON.stringify(body) });
}

export function synthesizeToolProposal(body: {
  problem: string;
  capability_context?: string;
}): Promise<Record<string, unknown>> {
  return request("/api/tools/synthesize", { method: "POST", body: JSON.stringify(body) });
}

export function observePrefetchPattern(body: {
  principal_id: string;
  event_key: string;
  capability_id: string;
  hour_local: number;
}): Promise<{ proposal: Record<string, unknown>; execution_performed: boolean }> {
  return request("/api/prefetch/observe", { method: "POST", body: JSON.stringify(body) });
}

export function getPrefetchProposals(principalId: string, limit = 20): Promise<{ items: Record<string, unknown>[]; count: number }> {
  return request("/api/prefetch/proposals?principal_id=" + encodeURIComponent(principalId) + "&limit=" + limit);
}
