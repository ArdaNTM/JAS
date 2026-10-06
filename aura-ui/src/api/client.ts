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
    let detail =
      `API request failed: ${response.status}`;

    try {
      const body =
        (await response.json()) as {
          detail?: string;
        };

      if (
        typeof body.detail === "string" &&
        body.detail.length > 0
      ) {
        detail = body.detail;
      }
    } catch {
      // Keep HTTP status error.
    }

    throw new Error(detail);
  }

  return response.json() as Promise<T>;
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

