import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useLoginState, useTaskHistory } from "../hooks/use-tasks";
import { TaskCard } from "../components/TaskCard";
import { I18nProvider } from "../i18n";
import { ApiError } from "../lib/api";

vi.mock("../hooks/use-tasks", async () => {
  const actual = await vi.importActual<typeof import("../hooks/use-tasks")>("../hooks/use-tasks");
  return { ...actual, useTaskHistory: vi.fn(), useLoginState: vi.fn() };
});

const mockedUseTaskHistory = vi.mocked(useTaskHistory);
const mockedUseLoginState = vi.mocked(useLoginState);

const task = {
  id: "task-1", goods_id: "418", stock_url: "https://nocix.net/out-of-stock/?id=418", cart_url: "https://nocix.net/cart/?id=418",
  target_price: 10, wait_interval: 5, operating_system: "debian" as const, email: "buyer@example.com", new_customer: false as const,
   payment_method: "paypal" as const, auto_submit: true, proxy_mode: "inherit" as const, proxy_configured: false, effective_proxy_configured: false, password_configured: true, status: "stopped" as const, last_stock_status: null,
  last_checked_at: null, last_error: null,
};

describe("TaskCard operation locking", () => {
  beforeEach(() => {
    localStorage.setItem("nocix-language", "en-US");
    mockedUseLoginState.mockReturnValue({ data: undefined, isLoading: false, error: null } as ReturnType<typeof useLoginState>);
  });
  it("disables edit, delete, and history while a mutation is pending", () => {
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={task} busy onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);
    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /history/i })).toBeDisabled();
  });

  it("announces task history query failures as alerts", async () => {
    const user = userEvent.setup();
    mockedUseTaskHistory.mockReturnValue({
      isLoading: false,
      error: new Error("history unavailable"),
      data: undefined,
    } as ReturnType<typeof useTaskHistory>);
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={task} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await user.click(screen.getByRole("button", { name: /history/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load history/i);
  });

  it.each(["unknown", "submitted_pending_confirmation"] as const)(
    "blocks lifecycle actions for %s tasks and explains manual confirmation",
    (status) => {
      render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

      expect(screen.queryByRole("button", { name: /start monitor/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /check now/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /stop|pause|resume/i })).not.toBeInTheDocument();
      expect(screen.getByText(/manual confirmation required/i)).toBeInTheDocument();
      expect(screen.getByText(/cannot retry automatically/i)).toBeInTheDocument();
    },
  );

  it("lets a user explicitly retry an ordinary failed task", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "failed", last_error: "price mismatch" }} onAction={onAction} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await user.click(screen.getByRole("button", { name: /start monitor/i }));

    expect(onAction).toHaveBeenCalledWith("start");
    expect(screen.getByText("price mismatch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /check now/i })).not.toBeInTheDocument();
  });

  it("locks successful tasks to history and delete", () => {
    const onAction = vi.fn();
    const onEdit = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "success" }} onAction={onAction} onEdit={onEdit} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    expect(screen.queryByRole("button", { name: /start monitor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /check now/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /history/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it.each(["running", "checking", "ordering"] as const)(
    "locks check and edit for active %s tasks while retaining pause/stop controls",
    (status) => {
      render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

      expect(screen.queryByRole("button", { name: /check now/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /pause/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
    },
  );

  it("does not add a dollar sign to an already-formatted observed price", async () => {
    mockedUseTaskHistory.mockReturnValue({
      isLoading: false,
      error: null,
      data: [{ id: 1, task_id: "task-1", status: "success", observed_price: "$59.00", error: null, created_at: "2026-08-11T00:00:00Z" }],
    } as ReturnType<typeof useTaskHistory>);
    const user = userEvent.setup();
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={task} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await user.click(screen.getByRole("button", { name: /history/i }));

    expect(screen.getByText("$59.00")).toBeInTheDocument();
    expect(screen.queryByText("$$59.00")).not.toBeInTheDocument();
  });

  it("uses effective global proxy status for inherited tasks without showing a URL", () => {
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, effective_proxy_configured: true }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("proxy.example");
  });

  it("locks normal actions while waiting for an email code and exposes safe login controls", () => {
    mockedUseLoginState.mockReturnValue({
      data: { task_id: "task-1", status: "waiting_for_email_code", waiting: true, attempts: 2, remaining_seconds: 87, last_error: "invalid verification code" },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useLoginState>);
    render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "waiting_for_email_code" }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    expect(screen.getByRole("status")).toHaveTextContent(/waiting for email verification code/i);
    expect(screen.getByText(/2 attempts/i)).toBeInTheDocument();
    expect(screen.getByText(/87 seconds remaining/i)).toBeInTheDocument();
    expect(screen.getByText("invalid verification code")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enter verification code/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel login/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start monitor|pause|resume|check now|edit|delete|stop/i })).not.toBeInTheDocument();
  });

  it.each(["login_first", "login_second"] as const)(
    "keeps pause and stop available during %s while locking edit, delete, and check",
    (status) => {
      const onAction = vi.fn();
      render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status }} onAction={onAction} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

      expect(screen.getByRole("button", { name: /pause/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /check now/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
    },
  );

  it("removes the code dialog when live login state becomes terminal", async () => {
    mockedUseLoginState.mockReturnValue({
      data: { task_id: "task-1", status: "waiting_for_email_code", waiting: true, attempts: 1, remaining_seconds: 60, last_error: null },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLoginState>);
    const view = render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "waiting_for_email_code" }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await userEvent.setup().click(screen.getByRole("button", { name: /enter verification code/i }));
    expect(screen.getByRole("dialog", { name: /enter email verification code/i })).toBeInTheDocument();

    mockedUseLoginState.mockReturnValue({
      data: { task_id: "task-1", status: "failed", waiting: false, attempts: 1, remaining_seconds: 0, last_error: "verification timed out" },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLoginState>);
    view.rerender(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "waiting_for_email_code" }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await waitFor(() => expect(screen.queryByRole("dialog", { name: /enter email verification code/i })).not.toBeInTheDocument());
    expect(screen.getByText("verification timed out")).toBeInTheDocument();
  });

  it("removes waiting UI immediately when a 409 arrives with retained waiting data", async () => {
    mockedUseLoginState.mockReturnValue({
      data: { task_id: "task-1", status: "waiting_for_email_code", waiting: true, attempts: 1, remaining_seconds: 60, last_error: null },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLoginState>);
    const view = render(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "waiting_for_email_code" }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    await userEvent.setup().click(screen.getByRole("button", { name: /enter verification code/i }));
    expect(screen.getByRole("dialog", { name: /enter email verification code/i })).toBeInTheDocument();

    mockedUseLoginState.mockReturnValue({
      data: { task_id: "task-1", status: "waiting_for_email_code", waiting: true, attempts: 1, remaining_seconds: 60, last_error: null },
      isLoading: false,
      error: new ApiError(409, "Login verification is not available"),
    } as unknown as ReturnType<typeof useLoginState>);
    view.rerender(<QueryClientProvider client={new QueryClient()}><I18nProvider initialLanguage="en-US"><TaskCard task={{ ...task, status: "waiting_for_email_code" }} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} /></I18nProvider></QueryClientProvider>);

    expect(screen.queryByRole("dialog", { name: /enter email verification code/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /enter verification code|cancel login/i })).not.toBeInTheDocument();
  });
});
