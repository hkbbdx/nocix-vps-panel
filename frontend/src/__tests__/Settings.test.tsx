import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { setApiKey } from "../lib/api";
import { Settings } from "../pages/Settings";

describe("Settings payment wording", () => {
  it("uses safe PayPal account-method wording", async () => {
    setApiKey("test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      environment: "test",
      browser_configured: true,
      api_key_configured: true,
      encryption_key_configured: true,
      telegram_enabled: false,
      telegram_configured: false,
      log_level: "INFO",
    }), { status: 200 }));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><Settings /></QueryClientProvider>);

    expect(await screen.findByText("Payment handling")).toBeInTheDocument();
    expect(screen.getByText("not used by panel")).toBeInTheDocument();
    expect(document.body.textContent).toContain("not used by panel");
  });
});
