const API_KEY_STORAGE = "nocix-api-key";
export const unauthorizedEvent = "nocix:unauthorized";
export const logoutEvent = "nocix:logout";
export type ApiMessageKey = "api.unauthorized" | "api.requestFailed" | "api.invalidResponse";
export type Translate = (key: string) => string;

export function getApiKey(): string | null {
  return sessionStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(value: string): void {
  sessionStorage.setItem(API_KEY_STORAGE, value);
}

export function clearApiKey(): void {
  sessionStorage.removeItem(API_KEY_STORAGE);
}

export class ApiError extends Error {
  status: number;
  messageKey?: ApiMessageKey;

  constructor(status: number, message: string, messageKey?: ApiMessageKey) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.messageKey = messageKey;
  }
}

export function formatApiError(error: unknown, t: Translate, fallbackKey: string): string {
  if (error instanceof ApiError && error.messageKey) return t(error.messageKey);
  return error instanceof Error && error.message ? error.message : t(fallbackKey);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "", "api.requestFailed");
  }
  if (response.status === 401) {
    clearApiKey();
    window.dispatchEvent(new CustomEvent(unauthorizedEvent, { detail: { messageKey: "api.unauthorized" } }));
    throw new ApiError(401, "", "api.unauthorized");
  }
  if (!response.ok) {
    let message = "";
    let hasBackendDetail = false;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
        hasBackendDetail = true;
      }
    } catch {
      // Use the translated client fallback when the server has no JSON body.
    }
    throw new ApiError(response.status, message, hasBackendDetail ? undefined : "api.requestFailed");
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(0, "", "api.invalidResponse");
  }
}

export const api = {
  tasks: {
    list: () => request<import("./types").Task[]>("/api/tasks"),
    create: (input: import("./types").TaskInput) =>
      request<import("./types").Task>("/api/tasks", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (id: string, input: Partial<import("./types").TaskInput>) =>
      request<import("./types").Task>(`/api/tasks/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    remove: (id: string) => request<void>(`/api/tasks/${id}`, { method: "DELETE" }),
    action: (id: string, action: "start" | "pause" | "resume" | "stop" | "check") =>
      request<unknown>(`/api/tasks/${id}/${action}`, { method: "POST" }),
    history: (id: string) =>
      request<import("./types").TaskHistoryEntry[]>(`/api/tasks/${id}/history`),
  },
  stats: () => request<import("./types").Stats>("/api/stats"),
  orders: {
    list: () => request<import("./types").Order[]>("/api/orders?limit=500"),
    clear: () => request<void>("/api/orders", { method: "DELETE" }),
  },
  logs: {
    list: (taskId?: string, level?: string) => {
      const params = new URLSearchParams({ limit: "500" });
      if (taskId) params.set("task_id", taskId);
      if (level) params.set("level", level);
      return request<import("./types").LogEntry[]>(`/api/logs?${params}`);
    },
    clear: () => request<void>("/api/logs", { method: "DELETE" }),
  },
  settings: {
    get: () => request<import("./types").RuntimeSettings>("/api/settings"),
    update: (input: { telegram_enabled?: boolean; telegram_bot_token?: string; telegram_chat_id?: string }) =>
      request<import("./types").RuntimeSettings>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    testTelegram: () => request<{ success: boolean; message: string }>("/api/telegram/test", { method: "POST" }),
  },
};
