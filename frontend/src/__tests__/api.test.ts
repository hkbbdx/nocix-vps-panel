import { api, getApiKey, setApiKey } from "../lib/api";

describe("API client", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("sends the session API key and clears it when the backend returns 401", async () => {
    setApiKey("session-secret");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Unauthorized", { status: 401, statusText: "Unauthorized" }),
    );

    const unauthorized = await api.stats().catch((error) => error);
    expect(unauthorized).toMatchObject({ status: 401, messageKey: "api.unauthorized" });
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/stats",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    const headers = fetchSpy.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("X-API-Key")).toBe("session-secret");
    expect(getApiKey()).toBeNull();
  });

  it("marks generic request failures as client-generated while preserving backend details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Backend detail stays raw" }), { status: 503, statusText: "Service Unavailable" }));

    const backendError = await api.stats().catch((error) => error);
    expect(backendError.status).toBe(503);
    expect(backendError.message).toBe("Backend detail stays raw");
    expect(backendError.messageKey).toBeUndefined();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const requestError = await api.stats().catch((error) => error);
    expect(requestError).toMatchObject({ messageKey: "api.requestFailed" });
  });

  it("marks malformed successful JSON as a client-generated response error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("not-json", { status: 200 }));

    const error = await api.stats().catch((caught) => caught);

    expect(error).toMatchObject({ messageKey: "api.invalidResponse" });
    expect(error.message).toBe("");
  });

  it("sends proxy settings and proxy tests to the protected endpoints without changing the secret", async () => {
    setApiKey("proxy-session-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        proxy_enabled: true,
        proxy_configured: true,
        proxy_display: "http://proxy.example.com:8080",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        success: true,
        proxy: "http://proxy.example.com:8080",
        message: "Proxy connection successful.",
      }), { status: 200 }));

    await api.settings.update({ proxy_enabled: true, proxy_url: "http://proxy-user:proxy-secret@proxy.example.com:8080" });
    const testResult = await api.proxy.test();

    expect(fetchSpy.mock.calls[0][0]).toBe("/api/settings");
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({
      proxy_enabled: true,
      proxy_url: "http://proxy-user:proxy-secret@proxy.example.com:8080",
    });
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/proxy/test");
    expect(fetchSpy.mock.calls[1][1]?.method).toBe("POST");
    expect((fetchSpy.mock.calls[0][1]?.headers as Headers).get("X-API-Key")).toBe("proxy-session-key");
    expect((fetchSpy.mock.calls[1][1]?.headers as Headers).get("X-API-Key")).toBe("proxy-session-key");
    expect(testResult.proxy).toBe("http://proxy.example.com:8080");
  });

  it("sends an optional draft proxy URL in the test request body", async () => {
    setApiKey("proxy-session-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      success: true,
      proxy: "socks5://proxy.example.com:1080",
      message: "Proxy connection successful.",
    }), { status: 200 }));

    await api.proxy.test("socks5://draft-user:draft-pass@proxy.example.com:1080");

    expect(fetchSpy).toHaveBeenCalledWith("/api/proxy/test", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ proxy_url: "socks5://draft-user:draft-pass@proxy.example.com:1080" }),
    }));
  });

  it("uses the protected login-state, email-code, and cancel endpoints", async () => {
    setApiKey("login-session-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        task_id: "task-1", status: "waiting_for_email_code", waiting: true,
        attempts: 1, remaining_seconds: 120, last_error: null,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        task_id: "task-1", status: "login_second", waiting: false,
        attempts: 1, remaining_seconds: 0, last_error: null,
        result: "accepted", message: "verification accepted",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        task_id: "task-1", status: "stopped", waiting: false,
        attempts: 1, remaining_seconds: 0, last_error: "verification cancelled",
        result: "cancelled", message: "verification cancelled",
      }), { status: 200 }));

    await api.tasks.loginState("task-1");
    await api.tasks.submitEmailCode("task-1", "1234");
    await api.tasks.cancelLogin("task-1");

    expect(fetchSpy.mock.calls.map(([path, init]) => ({
      path,
      method: init?.method,
      body: init?.body,
      key: (init?.headers as Headers).get("X-API-Key"),
    }))).toEqual([
      { path: "/api/tasks/task-1/login-state", method: undefined, body: undefined, key: "login-session-key" },
      { path: "/api/tasks/task-1/email-code", method: "POST", body: JSON.stringify({ code: "1234" }), key: "login-session-key" },
      { path: "/api/tasks/task-1/login-cancel", method: "POST", body: undefined, key: "login-session-key" },
    ]);
  });
});
