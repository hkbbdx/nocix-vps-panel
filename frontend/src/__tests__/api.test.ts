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

    await expect(api.stats()).rejects.toMatchObject({ status: 401 });
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/stats",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    const headers = fetchSpy.mock.calls[0][1]?.headers as Headers;
    expect(headers.get("X-API-Key")).toBe("session-secret");
    expect(getApiKey()).toBeNull();
  });
});
