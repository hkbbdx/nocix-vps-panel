import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { AuthGate } from "../components/AuthGate";
import { unauthorizedEvent, setApiKey } from "../lib/api";

describe("AuthGate", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("does not render task content or query tasks before an API key is accepted", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthGate>
          <div>Protected task console</div>
        </AuthGate>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: /api key/i })).toBeInTheDocument();
    expect(screen.queryByText("Protected task console")).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/tasks"),
      expect.anything(),
    );
  });

  it("clears cached query data when the session is unauthorized", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    setApiKey("old-key");
    queryClient.setQueryData(["tasks"], [{ id: "old-task" }]);

    render(
      <QueryClientProvider client={queryClient}>
        <AuthGate><div>Protected task console</div></AuthGate>
      </QueryClientProvider>,
    );

    await act(async () => {
      window.dispatchEvent(new Event(unauthorizedEvent));
    });

    expect(queryClient.getQueryData(["tasks"])).toBeUndefined();
    expect(sessionStorage.getItem("nocix-api-key")).toBeNull();
    expect(screen.getByRole("heading", { name: /api key/i })).toBeInTheDocument();
  });
});
