import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Layout } from "../components/Layout";
import { setApiKey } from "../lib/api";
import { I18nProvider } from "../i18n";

function setViewport(isMobile: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: isMobile,
    media: "(max-width: 680px)",
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("responsive navigation", () => {
  beforeEach(() => localStorage.setItem("nocix-language", "en-US"));
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the closed rail hidden from keyboard focus and closes with Escape", async () => {
    const user = userEvent.setup();
    setViewport(true);
    setApiKey("test-key");
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><MemoryRouter><Layout><div>Content</div></Layout></MemoryRouter></I18nProvider></QueryClientProvider>);
    const menu = screen.getByRole("button", { name: /open navigation/i });
    const rail = screen.getByRole("complementary", { hidden: true });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-controls", "mobile-navigation");
    expect(rail).toHaveAttribute("aria-hidden", "true");
    expect(rail).toHaveAttribute("inert");
    await user.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(rail).toHaveAttribute("aria-hidden", "false");
    await user.keyboard("{Escape}");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(document.activeElement).toBe(menu);
  });

  it("keeps the desktop rail exposed and interactive", async () => {
    const user = userEvent.setup();
    setViewport(false);
    setApiKey("test-key");
    const queryClient = new QueryClient();
    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><MemoryRouter><Layout><div>Content</div></Layout></MemoryRouter></I18nProvider></QueryClientProvider>);

    const rail = screen.getByRole("complementary");
    const tasksLink = screen.getByRole("link", { name: /tasks/i });
    const signOut = screen.getByRole("button", { name: /sign out/i });
    expect(rail).not.toHaveAttribute("aria-hidden");
    expect(rail).not.toHaveAttribute("inert");
    expect(tasksLink).not.toHaveAttribute("tabindex", "-1");
    expect(signOut).not.toBeDisabled();
    tasksLink.focus();
    expect(document.activeElement).toBe(tasksLink);
    await user.click(signOut);
    expect(sessionStorage.getItem("nocix-api-key")).toBeNull();
  });
});
