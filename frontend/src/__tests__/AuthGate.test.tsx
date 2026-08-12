import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { AuthGate } from "../components/AuthGate";
import { logoutEvent, unauthorizedEvent } from "../lib/api";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "../i18n";

describe("AuthGate", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
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
      <QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><AuthGate><div>Protected task console</div></AuthGate></I18nProvider></QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: "API key" })).toBeInTheDocument();
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
    queryClient.setQueryData(["tasks"], [{ id: "old-task" }]);

    render(
      <QueryClientProvider client={queryClient}><I18nProvider initialLanguage="en-US"><AuthGate><div>Protected task console</div></AuthGate></I18nProvider></QueryClientProvider>,
    );

    await act(async () => {
      window.dispatchEvent(new Event(unauthorizedEvent));
    });

    expect(queryClient.getQueryData(["tasks"])).toBeUndefined();
    expect(sessionStorage.getItem("nocix-api-key")).toBeNull();
     expect(screen.getByRole("heading", { name: "API key" })).toBeInTheDocument();
  });

  it("uses the selected language for unauthorized feedback after switching", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="zh-CN"><AuthGate><div>Protected task console</div></AuthGate></I18nProvider></QueryClientProvider>);
    await user.click(screen.getByRole("button", { name: /English/i }));
    await act(async () => window.dispatchEvent(new Event(unauthorizedEvent)));

    expect(screen.getByRole("alert")).toHaveTextContent("API key rejected. Enter a valid key to continue.");
  });

  it("uses a dedicated localized message for manual logout after switching", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><I18nProvider initialLanguage="zh-CN"><AuthGate><div>Protected task console</div></AuthGate></I18nProvider></QueryClientProvider>);
    await user.click(screen.getByRole("button", { name: /English/i }));
    await act(async () => window.dispatchEvent(new Event(logoutEvent)));

    expect(screen.getByRole("alert")).toHaveTextContent("You have been signed out.");
    expect(screen.queryByText("API key rejected. Enter a valid key to continue.")).not.toBeInTheDocument();
  });
});
