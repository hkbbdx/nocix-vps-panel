export type UpdateType = "feat" | "fix" | "docs" | "security";

export interface UpdateCopy {
  title: string;
  items: string[];
}

export interface UpdateEntry {
  date: string;
  commit: string;
  type: UpdateType;
  zh: UpdateCopy;
  en: UpdateCopy;
}

export const updates: UpdateEntry[] = [
  {
    date: "2026-08-15",
    commit: "9fff23b",
    type: "feat",
    zh: { title: "两阶段登录流程", items: ["支持分阶段完成已有账户登录。", "登录状态会在同一任务中继续推进。"] },
    en: { title: "Two-stage login flow", items: ["Existing-account login now completes in separate stages.", "The same task continues through the login state."] },
  },
  {
    date: "2026-08-15",
    commit: "f481374",
    type: "feat",
    zh: { title: "HTTP 和 SOCKS5 代理", items: ["支持全局代理和任务级代理选择。", "代理配置会在连接前校验格式。"] },
    en: { title: "HTTP and SOCKS5 proxies", items: ["Added global and task-level proxy selection.", "Proxy formats are checked before connecting."] },
  },
  {
    date: "2026-08-12",
    commit: "52a3ad5",
    type: "fix",
    zh: { title: "任务状态与时区修正", items: ["修正首页任务状态统计。", "统一显示本地会话时间。"] },
    en: { title: "Task state and timezone fixes", items: ["Corrected task-state metrics on the overview.", "Standardized local-session time display."] },
  },
  {
    date: "2026-08-12",
    commit: "addd065",
    type: "fix",
    zh: { title: "监控日志持久化", items: ["保存 worker 运行日志，便于回看事件。", "日志显示保持脱敏并限制数量。"] },
    en: { title: "Persisted monitoring logs", items: ["Worker runtime logs are retained for event review.", "Rendered logs remain redacted and capped."] },
  },
  {
    date: "2026-08-12",
    commit: "7a67b65",
    type: "feat",
    zh: { title: "简体中文和英文界面", items: ["面板默认使用简体中文。", "可从导航或登录页切换英文。"] },
    en: { title: "Simplified Chinese and English UI", items: ["The panel defaults to Simplified Chinese.", "Switch to English from navigation or the login screen."] },
  },
  {
    date: "2026-08-12",
    commit: "154daa1",
    type: "feat",
    zh: { title: "初始 NOCIX 控制面板", items: ["提供任务、订单、日志和设置页面。", "支持监控库存并执行明确的下单流程。"] },
    en: { title: "Initial NOCIX control panel", items: ["Added task, order, log, and settings pages.", "Supports availability monitoring and explicit ordering flows."] },
  },
];

export function recentUpdates(limit = 5): UpdateEntry[] {
  return updates.slice(0, Math.max(0, limit));
}
