import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthGate } from "../components/AuthGate";
import { Layout } from "../components/Layout";
import { I18nProvider, useTranslation } from "../i18n";
import { Orders } from "../pages/Orders";
import { Logs } from "../pages/Logs";
import { setApiKey } from "../lib/api";
import { LanguageSwitcher } from "../components/LanguageSwitcher";

function Probe() {
  const { language, setLanguage, t } = useTranslation();
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="message">{t("tasks.count", { count: 3 })}</span>
      <button onClick={() => setLanguage("en-US")}>switch</button>
    </div>
  );
}

function renderWithI18n(ui: React.ReactNode) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

describe("bilingual panel", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    document.documentElement.lang = "en";
    document.title = "NOCIX Control Console";
    vi.restoreAllMocks();
  });

  it("defaults to Simplified Chinese", () => {
    renderWithI18n(<Probe />);

    expect(screen.getByTestId("language")).toHaveTextContent("zh-CN");
    expect(screen.getByTestId("message")).toHaveTextContent("3 个任务");
  });

  it("switches to English and updates translated text", () => {
    renderWithI18n(<Probe />);

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("language")).toHaveTextContent("en-US");
    expect(screen.getByTestId("message")).toHaveTextContent("3 tasks");
  });

  it("provides bilingual update page labels", () => {
    function UpdatesLabelsProbe() {
      const { t } = useTranslation();
      return <span>{t("updates.eyebrow")}|{t("updates.title")}|{t("updates.subtitle")}|{t("updates.recent")}|{t("updates.viewAll")}|{t("updates.date")}|{t("updates.type.feat")}</span>;
    }

    renderWithI18n(<UpdatesLabelsProbe />);
    expect(screen.getByText(/版本记录\|更新日志\|/)).toBeInTheDocument();
  });

  it("updates document language and title when the selected language changes", () => {
    renderWithI18n(<Probe />);

    expect(document.documentElement.lang).toBe("zh-CN");
    expect(document.title).toBe("NOCIX 控制台");
    fireEvent.click(screen.getByRole("button", { name: "switch" }));
    expect(document.documentElement.lang).toBe("en-US");
    expect(document.title).toBe("NOCIX Control Console");
  });

  it("persists the selected language across provider remounts", () => {
    const first = renderWithI18n(<Probe />);
    fireEvent.click(screen.getByRole("button", { name: "switch" }));
    first.unmount();

    renderWithI18n(<Probe />);

    expect(screen.getByTestId("language")).toHaveTextContent("en-US");
  });

  it("falls back to Simplified Chinese for invalid storage", () => {
    localStorage.setItem("nocix-language", "fr-FR");

    renderWithI18n(<Probe />);

    expect(screen.getByTestId("language")).toHaveTextContent("zh-CN");
  });

  it("renders Simplified Chinese when storage access throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("storage blocked"); });

    renderWithI18n(<Probe />);

    expect(screen.getByTestId("language")).toHaveTextContent("zh-CN");
  });

  it("falls back to Simplified Chinese for a missing translation key", () => {
    function MissingKeyProbe() {
      const { t } = useTranslation();
      return <span>{t("missing.key")}</span>;
    }

    renderWithI18n(<MissingKeyProbe />);

    expect(screen.getByText("missing.key")).toBeInTheDocument();
  });

  it("uses Simplified Chinese in the no-provider translation fallback", () => {
    function DefaultContextProbe() {
      const { language, t } = useTranslation();
      return <span>{language}:{t("auth.title")}</span>;
    }

    render(<DefaultContextProbe />);

    expect(screen.getByText("zh-CN:API 密钥")).toBeInTheDocument();
  });

  it("does not fail when language persistence writes throw", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("storage blocked"); });

    expect(() => renderWithI18n(<LanguageSwitcher />)).not.toThrow();
    fireEvent.click(screen.getByRole("button", { name: /English/i }));
    expect(screen.getByRole("button", { name: /简体中文/i })).toBeInTheDocument();
  });

  it("exposes the language switcher before authentication", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <AuthGate><div>protected</div></AuthGate>
        </I18nProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: /English/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API 密钥" })).toBeInTheDocument();
  });

  it("exposes the language switcher in the authenticated layout", () => {
    const queryClient = new QueryClient();
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter><Layout><div>content</div></Layout></MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: /English/i })).toBeInTheDocument();
  });

  it("leaves raw order errors and browser log messages unchanged", async () => {
    const rawOrderError = "PayPal gateway returned HTTP 502";
    const rawLogMessage = "Browser console: Unexpected token < in JSON";
    setApiKey("test-key");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      if (path.includes("/api/orders")) return new Response(JSON.stringify([{ id: 1, task_id: "task-1", status: "failed", observed_price: null, error: rawOrderError, created_at: "2026-08-11T00:00:00Z" }]));
      if (path.includes("/api/logs")) return new Response(JSON.stringify([{ id: 2, level: "ERROR", task_id: null, message: rawLogMessage, created_at: "2026-08-11T00:00:00Z" }]));
      if (path.includes("/api/tasks")) return new Response("[]");
      return new Response("{}", { status: 200 });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const view = render(<QueryClientProvider client={queryClient}><I18nProvider><Orders /></I18nProvider></QueryClientProvider>);
    expect(await screen.findByText(rawOrderError)).toBeInTheDocument();
    view.unmount();
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><I18nProvider><Logs /></I18nProvider></QueryClientProvider>);
    expect(await screen.findByText(rawLogMessage)).toBeInTheDocument();
  });
});
