import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "../pages/Dashboard";
import { Updates } from "../pages/Updates";
import { Layout } from "../components/Layout";
import { I18nProvider, useTranslation } from "../i18n";
import { recentUpdates, updates } from "../lib/updates";

vi.mock("../hooks/use-dashboard", () => ({
  useDashboard: () => ({ data: undefined, error: null }),
}));

vi.mock("../hooks/use-tasks", () => ({
  useTasks: () => ({ data: [], isLoading: false, error: null }),
}));

function renderWithProviders(ui: React.ReactNode, language: "zh-CN" | "en-US" = "zh-CN") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLanguage={language}>
        <MemoryRouter>{ui}</MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function LanguageControl() {
  const { setLanguage } = useTranslation();
  return <button onClick={() => setLanguage("en-US")}>switch updates language</button>;
}

describe("release updates", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("contains safe newest-first entries with valid dates and short hashes", () => {
    expect(updates.length).toBeGreaterThanOrEqual(5);
    expect(updates).toEqual([...updates].sort((a, b) => b.date.localeCompare(a.date)));
    for (const entry of updates) {
      expect(entry.date).toMatch(/^20\d{2}-\d{2}-\d{2}$/);
      expect(entry.commit).toMatch(/^[0-9a-f]{7,12}$/);
      expect(["feat", "fix", "docs", "security"]).toContain(entry.type);
      expect(entry.zh.title).toBeTruthy();
      expect(entry.en.title).toBeTruthy();
      expect(entry.zh.items.length).toBeGreaterThan(0);
      expect(entry.en.items.length).toBe(entry.zh.items.length);
      expect(JSON.stringify(entry)).not.toMatch(/api[_ -]?key|password|token|secret|验证码|凭据/i);
    }
  });

  it("returns only the requested number of recent entries", () => {
    expect(recentUpdates()).toHaveLength(5);
    expect(recentUpdates(2)).toEqual(updates.slice(0, 2));
  });

  it("shows five recent entries on the dashboard and links to all updates", () => {
    renderWithProviders(<Dashboard />);

    expect(screen.getByRole("heading", { name: "最近更新" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看全部更新/i })).toHaveAttribute("href", "/updates");
    expect(screen.getAllByRole("article", { name: /更新/ })).toHaveLength(5);
  });

  it("shows every entry on the updates page", () => {
    renderWithProviders(<Updates />);

    expect(screen.getByRole("heading", { name: "更新日志", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: /更新/ })).toHaveLength(updates.length);
  });

  it("switches dynamic update copy with the selected language", async () => {
    renderWithProviders(<><LanguageControl /><Updates /></>, "zh-CN");
    expect(screen.getByText(updates[0].zh.title)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "switch updates language" }));
    await waitFor(() => expect(screen.getByText(updates[0].en.title)).toBeInTheDocument());
  });

  it("adds updates to the primary navigation", () => {
    renderWithProviders(<Layout><div>Content</div></Layout>, "zh-CN");

    expect(screen.getByRole("link", { name: /更新日志/ })).toHaveAttribute("href", "/updates");
  });
});
