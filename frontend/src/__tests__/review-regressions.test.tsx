import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Layout } from "../components/Layout";
import { TaskCard } from "../components/TaskCard";
import { I18nProvider, useTranslation } from "../i18n";
import { Logs } from "../pages/Logs";
import { getTaskActionFeedbackKey } from "../pages/Tasks";

vi.mock("../hooks/use-tasks", async () => {
  const actual = await vi.importActual<typeof import("../hooks/use-tasks")>("../hooks/use-tasks");
  return { ...actual, useTaskHistory: vi.fn(() => ({ isLoading: false, error: null, data: undefined })) };
});

const task = {
  id: "task-1", goods_id: "418", stock_url: "https://nocix.net/out-of-stock/?id=418", cart_url: "https://nocix.net/cart/?id=418",
  target_price: 10, wait_interval: 5, operating_system: "debian" as const, email: "buyer@example.com", new_customer: false as const,
  payment_method: "paypal" as const, auto_submit: true, password_configured: true, status: "stopped" as const, last_stock_status: null,
  last_checked_at: null, last_error: null,
};

function renderInLanguage(language: "zh-CN" | "en-US", ui: React.ReactNode) {
  localStorage.setItem("nocix-language", language);
  return render(<QueryClientProvider client={new QueryClient()}><I18nProvider>{ui}</I18nProvider></QueryClientProvider>);
}

function ActionFeedbackProbe({ action }: { action: "start" | "pause" | "resume" | "stop" | "check" }) {
  const { t } = useTranslation();
  return <span>{t(getTaskActionFeedbackKey(action))}</span>;
}

describe("bilingual review regressions", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.setItem("nocix-api-key", "test-key");
    vi.restoreAllMocks();
  });

  it.each([
    ["start", "监控已启动。", "Monitor started."],
    ["pause", "任务已暂停。", "Task paused."],
    ["resume", "任务已恢复。", "Task resumed."],
    ["stop", "任务已停止。", "Task stopped."],
    ["check", "检查已开始。", "Check started."],
  ] as const)("localizes the %s task action feedback", (action, zh, en) => {
    const expectedKey = { start: "tasks.started", pause: "tasks.paused", resume: "tasks.resumed", stop: "tasks.stopped", check: "tasks.checkStarted" }[action];
    expect(getTaskActionFeedbackKey(action)).toBe(expectedKey);
    const view = renderInLanguage("zh-CN", <ActionFeedbackProbe action={action} />);
    expect(screen.getByText(zh)).toBeInTheDocument();
    view.unmount();
    renderInLanguage("en-US", <ActionFeedbackProbe action={action} />);
    expect(screen.getByText(en)).toBeInTheDocument();
  });

  it("localizes the mobile close button, task OS label, and generated log task prefix", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const layout = renderInLanguage("zh-CN", <MemoryRouter><Layout><div>content</div></Layout></MemoryRouter>);
    expect(screen.getByRole("button", { name: "关闭导航" })).toBeInTheDocument();
    layout.unmount();

    const taskView = renderInLanguage("zh-CN", <TaskCard task={task} onAction={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getAllByText("操作系统").length).toBeGreaterThan(0);
    taskView.unmount();

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      if (path.includes("/api/logs")) return new Response(JSON.stringify([{ id: 1, level: "INFO", task_id: "abcdef123456", message: "raw log", created_at: "2026-08-11T00:00:00Z" }]));
      if (path.includes("/api/tasks")) return new Response("[]");
      return new Response("{}");
    });
    renderInLanguage("en-US", <Logs />);
    await expect(screen.findByText(/task abcdef12/i)).resolves.toBeTruthy();
  });
});
