import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { Orders } from "../pages/Orders";
import { setApiKey } from "../lib/api";
import { I18nProvider } from "../i18n";

describe("destructive mutation feedback", () => {
  beforeEach(() => localStorage.setItem("nocix-language", "en-US"));
  it("shows an accessible error when clearing orders fails", async () => {
    const user = userEvent.setup();
    setApiKey("test-key");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.includes("/api/orders") && init?.method === "DELETE") {
        return new Response(JSON.stringify({ detail: "Order service unavailable" }), { status: 503 });
      }
      if (path.includes("/api/orders")) return new Response("[]", { status: 200 });
      if (path.includes("/api/tasks")) return new Response("[]", { status: 200 });
      return new Response("{}", { status: 200 });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><Orders /></I18nProvider></QueryClientProvider>);
    await user.click(await screen.findByRole("button", { name: /clear history/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/order service unavailable/i));
  });
});
