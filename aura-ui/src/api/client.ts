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
      apiError?.message ?? legacyDetail ?? `API request failed: ${response.status}`,
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
