import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { setApiKey } from "../lib/api";
import { Settings } from "../pages/Settings";
import { I18nProvider } from "../i18n";

describe("Settings payment wording", () => {
  beforeEach(() => localStorage.setItem("nocix-language", "en-US"));
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

    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><Settings /></I18nProvider></QueryClientProvider>);

    expect(await screen.findByText("Payment handling")).toBeInTheDocument();
    expect(screen.getByText("not used by panel")).toBeInTheDocument();
    expect(document.body.textContent).toContain("not used by panel");
  });

  it("saves and tests a proxy while clearing the URL from the rendered page and browser storage", async () => {
    const user = userEvent.setup();
    const secret = "http://proxy-user:proxy-secret@proxy.example.com:8080";
    setApiKey("settings-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === "/api/settings" && init?.method === "PUT") {
        return new Response(JSON.stringify({
          environment: "test", browser_configured: true, api_key_configured: true,
          encryption_key_configured: true, telegram_enabled: false, telegram_configured: false,
          log_level: "INFO", proxy_enabled: true, proxy_configured: true,
          proxy_display: "http://proxy.example.com:8080",
        }), { status: 200 });
      }
      if (path === "/api/proxy/test") {
        return new Response(JSON.stringify({ success: true, proxy: "http://proxy.example.com:8080", message: "Proxy connection successful." }), { status: 200 });
      }
      return new Response(JSON.stringify({
        environment: "test", browser_configured: true, api_key_configured: true,
        encryption_key_configured: true, telegram_enabled: false, telegram_configured: false,
        log_level: "INFO", proxy_enabled: false, proxy_configured: false,
      }), { status: 200 });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><Settings /></I18nProvider></QueryClientProvider>);

    expect(await screen.findByLabelText("Proxy URL")).toHaveAttribute("type", "password");
    await user.click(screen.getByLabelText("Enable global proxy"));
    await user.type(screen.getByLabelText("Proxy URL"), secret);
    await user.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => expect(fetchSpy.mock.calls.some(([input, init]) => input === "/api/settings" && init?.method === "PUT")).toBe(true));
    expect(screen.getByText(/proxy\.example\.com:8080/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(secret);
    expect(sessionStorage.getItem(secret)).toBeNull();
    expect(localStorage.getItem(secret)).toBeNull();
    expect(screen.getByLabelText("Proxy URL")).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Test proxy" }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith("/api/proxy/test", expect.objectContaining({ method: "POST" })));
    expect(screen.getByText(/Proxy connection successful\. \(http:\/\/proxy\.example\.com:8080\)/)).toBeInTheDocument();
  });

  it("tests the current enabled draft proxy without saving it", async () => {
    const user = userEvent.setup();
    const draft = "http://draft-user:draft-pass@draft.example.com:8080";
    setApiKey("settings-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === "/api/proxy/test") {
        expect(JSON.parse(String(init?.body))).toEqual({ proxy_url: draft });
        return new Response(JSON.stringify({ success: true, proxy: "http://draft.example.com:8080", message: "Proxy connection successful." }), { status: 200 });
      }
      return new Response(JSON.stringify({
        environment: "test", browser_configured: true, api_key_configured: true,
        encryption_key_configured: true, telegram_enabled: false, telegram_configured: false,
        log_level: "INFO", proxy_enabled: false, proxy_configured: false,
      }), { status: 200 });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><Settings /></I18nProvider></QueryClientProvider>);

    await screen.findByLabelText("Proxy URL");
    await user.click(screen.getByLabelText("Enable global proxy"));
    await user.type(screen.getByLabelText("Proxy URL"), draft);
    await user.click(screen.getByRole("button", { name: "Test proxy" }));

    await waitFor(() => expect(fetchSpy.mock.calls.some(([input]) => input === "/api/proxy/test")).toBe(true));
    expect(fetchSpy.mock.calls.some(([input, init]) => input === "/api/settings" && init?.method === "PUT")).toBe(false);
    expect(document.body.textContent).not.toContain(draft);
  });
});
