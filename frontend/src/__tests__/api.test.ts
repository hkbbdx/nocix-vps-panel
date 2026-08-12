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
});
