import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { useLoginState } from "../hooks/use-tasks";
import { setApiKey } from "../lib/api";

function Probe() {
  useLoginState("task-1", "waiting_for_email_code");
  return null;
}

describe("login state terminal refresh", () => {
  beforeEach(() => {
    setApiKey("test-key");
    vi.restoreAllMocks();
  });

  it("refreshes task, stats, logs, and orders after a 409 stops login polling", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Login verification is not available" }), { status: 409 }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");

    render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>);

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["tasks"] })));
    expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["stats"] }));
    expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["logs"] }));
    expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["orders"] }));
  });
});
