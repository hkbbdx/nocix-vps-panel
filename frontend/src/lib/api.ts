const API_KEY_STORAGE = "nocix-api-key";
export const unauthorizedEvent = "nocix:unauthorized";

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

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    clearApiKey();
    window.dispatchEvent(new Event(unauthorizedEvent));
    throw new ApiError(401, "Your API key is no longer valid.");
  }
  if (!response.ok) {
    let message = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail || message;
    } catch {
      // Keep the HTTP status message when the server has no JSON body.
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
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
