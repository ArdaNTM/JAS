export interface TaskRequest {
  goal: string;
}

export interface TaskResponse {
  task_id: string;
  status: string;
}

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

export function createTask(
  requestBody: TaskRequest,
): Promise<TaskResponse> {
  return request<TaskResponse>(
    "/api/tasks",
    {
      method: "POST",
      body: JSON.stringify(requestBody),
    },
  );
}

export function getTask(
  taskId: string,
): Promise<unknown> {
  return request(
    `/api/tasks/${taskId}`,
  );
}
