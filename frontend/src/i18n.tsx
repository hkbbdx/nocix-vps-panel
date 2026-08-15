import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Language = "zh-CN" | "en-US";
export type TranslationVariables = Record<string, string | number>;
export const LANGUAGE_STORAGE_KEY = "nocix-language";

const translations: Record<Language, Record<string, string>> = {
  "zh-CN": {
    "language.switchTo": "English",
    "language.current": "简体中文",
    "auth.eyebrow": "私有运维界面",
    "auth.title": "API 密钥",
    "auth.copy": "连接到你的 NOCIX worker 服务。密钥仅保留在此浏览器会话中。",
    "auth.keyLabel": "面板 API 密钥",
    "auth.checking": "检查中…",
    "auth.enter": "进入控制台",
    "auth.session": "会话级身份验证",
    "auth.enterKey": "请输入 API 密钥。",
    "auth.rejected": "API 密钥已被拒绝。请输入有效密钥后继续。",
    "auth.failed": "该 API 密钥无法通过面板身份验证。",
    "auth.loggedOut": "你已退出登录。",
    "document.title": "NOCIX 控制台",
    "api.unauthorized": "API 密钥已失效。请重新输入有效密钥。",
    "api.requestFailed": "请求失败。请检查网络连接后重试。",
    "api.invalidResponse": "服务器返回了无效响应。请稍后重试。",
    "nav.overview": "概览",
    "nav.tasks": "任务",
    "nav.orders": "订单",
    "nav.logs": "日志",
    "nav.settings": "设置",
    "nav.controlRoom": "控制室",
    "nav.primary": "主导航",
    "nav.close": "关闭导航",
    "nav.open": "打开导航",
    "nav.apiConnected": "API 已连接",
    "nav.sessionActive": "会话活跃",
    "nav.signOut": "退出登录",
    "top.context": "NOCIX / 运维",
    "top.title": "Worker 控制台",
    "top.live": "在线",
    "top.localSession": "本地会话",
    "dashboard.eyebrow": "worker 遥测",
    "dashboard.title": "概览",
    "dashboard.subtitle": "实时查看 NOCIX 可用性监控与结账队列。",
    "dashboard.newTask": "+ 新建任务",
    "dashboard.statsUnavailable": "统计信息不可用。请检查 API 连接并刷新。",
    "dashboard.activeWorkers": "活跃 worker",
    "dashboard.checkingNow": "{count} 个正在检查",
    "dashboard.availableStock": "可用库存",
    "dashboard.inCheckout": "{count} 个结账中",
    "dashboard.successfulOrders": "成功订单",
    "dashboard.successfulTasks": "{count} 个成功任务",
    "dashboard.failedAttempts": "失败尝试",
    "dashboard.failedTasks": "{count} 个失败任务",
    "dashboard.taskFleet": "任务集群",
    "dashboard.monitors": "监控概览",
    "dashboard.viewAll": "查看全部 →",
    "dashboard.couldNotLoadTasks": "无法加载任务。",
    "dashboard.noMonitors": "还没有监控",
    "dashboard.createWatcher": "创建第一个商品监控以开始接收库存信号。",
    "dashboard.createTask": "创建任务",
    "dashboard.latestSignal": "最新信号",
    "dashboard.systemHealth": "系统健康",
    "dashboard.apiService": "API 服务",
    "dashboard.workerManager": "Worker 管理器",
    "dashboard.browserSessions": "浏览器会话",
    "dashboard.latestError": "最新错误",
    "dashboard.operational": "运行正常",
    "dashboard.needsAttention": "需要关注",
    "dashboard.noRecentErrors": "近期无错误",
    "dashboard.loading": "正在加载遥测数据…",
    "tasks.eyebrow": "自动化 / 监控",
    "tasks.title": "任务",
    "tasks.subtitle": "使用每个任务独立保存的 NOCIX 账户运行商品监控。",
    "tasks.add": "+ 添加任务",
    "tasks.loading": "正在加载任务…",
    "tasks.loadError": "无法加载任务。请刷新页面后重试。",
    "tasks.emptyTitle": "任务集群为空",
    "tasks.emptyBody": "设置商品 ID、目标价格和现有 NOCIX 账户即可开始。",
    "tasks.createFirst": "创建第一个任务",
    "tasks.updated": "任务已更新。",
    "tasks.created": "任务已创建。",
    "tasks.checkStarted": "检查已开始。",
    "tasks.started": "监控已启动。",
    "tasks.paused": "任务已暂停。",
    "tasks.resumed": "任务已恢复。",
    "tasks.stopped": "任务已停止。",
    "tasks.savedError": "无法保存任务。",
    "tasks.actionFailed": "操作失败。",
    "tasks.deleteConfirm": "确定删除商品 {product} 的监控吗？这将删除其历史记录。",
    "tasks.deleted": "任务已删除。",
    "tasks.deleteError": "无法删除任务。",
    "tasks.count": "{count} 个任务",
    "orders.eyebrow": "结账结果",
    "orders.title": "订单",
    "orders.subtitle": "按时间记录已提交和被阻止的结账尝试。",
    "orders.refresh": "↻ 刷新",
    "orders.clear": "清除历史",
    "orders.clearConfirm": "确定清除全部订单历史吗？此操作无法撤销。",
    "orders.cleared": "订单历史已清除。",
    "orders.clearError": "无法清除订单历史。",
    "orders.loading": "正在加载订单…",
    "orders.loadError": "无法加载订单。",
    "orders.status": "状态",
    "orders.taskProduct": "任务 / 商品",
    "orders.observedPrice": "观测价格",
    "orders.targetPrice": "目标价格",
    "orders.result": "结果",
    "orders.timestamp": "时间",
    "orders.submitted": "已提交",
    "orders.emptyTitle": "没有订单尝试",
    "orders.emptyBody": "成功和失败的结账尝试会显示在这里。",
    "logs.eyebrow": "运行时输出",
    "logs.title": "日志",
    "logs.subtitle": "实时 worker 事件，已脱敏并限制为最多显示 500 条。",
    "logs.refresh": "↻ 刷新",
    "logs.clear": "清除日志",
    "logs.clearConfirm": "确定清除全部日志吗？此操作无法撤销。",
    "logs.cleared": "日志已清除。",
    "logs.clearError": "无法清除日志。",
    "logs.task": "任务",
    "logs.allTasks": "全部任务",
    "logs.level": "级别",
    "logs.allLevels": "全部级别",
    "logs.polling": "每 5 秒轮询",
    "logs.loading": "正在加载日志…",
    "logs.loadError": "无法加载日志。",
    "logs.system": "系统",
    "logs.taskPrefix": "任务 {id}",
    "logs.noMatch": "没有匹配的日志",
    "logs.emptyBody": "任务运行后，worker 活动会显示在这里。",
    "settings.eyebrow": "服务配置",
    "settings.title": "设置",
    "settings.subtitle": "查看运行时连接状态并更新安全的通知偏好。",
    "settings.loading": "正在加载设置…",
    "settings.loadError": "无法加载设置。",
    "settings.runtime": "运行时状态",
    "settings.connections": "服务连接",
    "settings.apiAuth": "API 身份验证",
    "settings.browser": "浏览器服务",
    "settings.encryption": "数据库加密",
    "settings.telegram": "Telegram",
    "settings.payment": "支付处理",
    "settings.notUsed": "面板未使用",
    "settings.notifications": "通知",
    "settings.delivery": "Telegram 投递",
    "settings.copy": "这里只能修改 Telegram 和代理设置。密钥会发送到后端，绝不会返回浏览器。",
    "settings.enableTelegram": "启用 Telegram 通知",
    "settings.notificationDetail": "接收库存、结账和 worker 故障事件。",
    "settings.botToken": "Bot token",
    "settings.replaceToken": "已配置，输入以替换",
    "settings.pasteToken": "粘贴 Bot token",
    "settings.chatId": "Chat ID",
    "settings.replaceChat": "已配置，输入以替换",
    "settings.enterChat": "输入 Telegram Chat ID",
    "settings.save": "保存设置",
    "settings.saving": "保存中…",
    "settings.test": "发送测试消息",
    "settings.testing": "测试中…",
    "settings.saved": "设置已保存。",
    "settings.saveError": "无法保存 Telegram 设置。",
    "settings.testFailed": "Telegram 测试失败。",
  "settings.configured": "已配置",
  "settings.notConfigured": "未配置",
    "settings.enabled": "已启用",
    "settings.disabled": "已停用",
    "task.editEyebrow": "编辑监控",
    "task.newEyebrow": "新建监控",
    "task.editTitle": "调整任务",
    "task.newTitle": "监控 NOCIX 商品",
    "task.dialogDescription": "配置 NOCIX 商品监控及其保存的账户结账设置。",
    "task.closeForm": "关闭任务表单",
    "task.productId": "商品 ID",
    "task.targetPrice": "目标价格",
    "task.interval": "检查间隔（秒）",
    "task.operatingSystem": "操作系统",
    "task.osDebian": "Debian",
    "task.osUbuntu": "Ubuntu",
    "task.email": "现有 NOCIX 邮箱",
    "task.password": "NOCIX 密码",
    "task.leaveUnchanged": "留空则不更改",
    "task.stockUrl": "库存 URL",
    "task.cartUrl": "购物车 URL",
    "task.optional": "可选",
    "task.derivedStock": "留空时根据商品 ID 生成",
    "task.derivedCart": "留空时根据商品 ID 生成",
    "task.paymentMethod": "支付方式：",
    "task.paypalCopy": "结账使用 NOCIX 中已保存的 PayPal。",
    "task.autoSubmit": "已启用自动提交",
    "task.autoSubmitCopy": "已确认：目标商品和价格匹配后提交一次。",
    "task.cancel": "取消",
    "task.saving": "保存中…",
    "task.saveChanges": "保存更改",
    "task.create": "创建任务",
    "task.productDigits": "商品 ID 只能包含数字。",
    "task.priceInvalid": "目标价格必须是大于零的有限数字。",
    "task.intervalInvalid": "检查间隔必须是至少 2 秒的有限整数。",
    "task.emailInvalid": "请输入有效的邮箱地址。",
    "task.accountRequired": "需要现有 NOCIX 邮箱和密码。",
    "task.passwordRequired": "此任务需要现有 NOCIX 密码。",
    "task.stockUrlInvalid": "库存 URL 必须是 NOCIX 主机上的有效 HTTP(S) 地址。",
    "task.cartUrlInvalid": "购物车 URL 必须是 NOCIX 主机上的有效 HTTP(S) 地址。",
    "task.proxy": "代理",
    "task.proxyMode": "代理模式",
    "task.proxyInherit": "继承全局代理",
    "task.proxyCustom": "使用自定义代理",
    "task.proxyDirect": "直连",
    "task.customProxyUrl": "自定义代理 URL",
    "task.proxyFormat": "http://host:port 或 socks5://user:password@host:port",
    "task.proxyUrlInvalid": "代理 URL 必须使用 http:// 或 socks5://，包含主机和端口，且不能包含查询参数或片段。",
    "task.target": "目标",
    "task.intervalShort": "间隔",
    "task.lastCheck": "上次检查",
    "task.never": "从未",
    "task.confirmation": "需要手动确认。",
    "task.noRetry": "无法自动重试。",
    "task.resume": "恢复",
    "task.pause": "暂停",
    "task.start": "启动监控",
    "task.check": "立即检查",
    "task.hideHistory": "隐藏历史",
    "task.history": "历史",
    "task.edit": "编辑",
    "task.stop": "停止",
    "task.delete": "删除",
    "task.loadingHistory": "正在加载历史…",
    "task.historyError": "无法加载历史。",
    "task.noPrice": "无价格",
    "task.noAttempts": "没有记录的订单尝试。",
    "status.stopped": "已停止",
    "status.running": "运行中",
    "status.checking": "检查中",
    "status.ordering": "下单中",
    "status.paused": "已暂停",
    "status.success": "成功",
    "status.failed": "失败",
    "status.unknown": "未知",
    "status.pending": "等待确认",
  },
  "en-US": {},
};

translations["en-US"] = {
  ...translations["zh-CN"],
  "language.switchTo": "简体中文", "language.current": "English",
  "auth.eyebrow": "Private operations interface", "auth.title": "API key", "auth.copy": "Connect to your NOCIX worker service. The key stays in this browser session only.", "auth.keyLabel": "Panel API key", "auth.checking": "Checking…", "auth.enter": "Enter console", "auth.session": "Session-scoped authentication", "auth.enterKey": "Enter an API key.", "auth.rejected": "API key rejected. Enter a valid key to continue.", "auth.failed": "That API key could not authenticate with the panel.", "auth.loggedOut": "You have been signed out.", "document.title": "NOCIX Control Console", "api.unauthorized": "Your API key is no longer valid. Enter a valid key to continue.", "api.requestFailed": "The request failed. Check your connection and try again.", "api.invalidResponse": "The server returned an invalid response. Try again later.",
  "nav.overview": "Overview", "nav.tasks": "Tasks", "nav.orders": "Orders", "nav.logs": "Logs", "nav.settings": "Settings", "nav.controlRoom": "Control room", "nav.primary": "Primary navigation", "nav.close": "Close navigation", "nav.open": "Open navigation", "nav.apiConnected": "API connected", "nav.sessionActive": "Session active", "nav.signOut": "Sign out", "top.context": "NOCIX / OPERATIONS", "top.title": "Worker control console", "top.live": "Live", "top.localSession": "Local session",
  "dashboard.eyebrow": "worker telemetry", "dashboard.title": "Overview", "dashboard.subtitle": "A live read on your NOCIX availability monitors and checkout queue.", "dashboard.newTask": "+ New task", "dashboard.statsUnavailable": "Stats unavailable. Check the API connection and refresh.", "dashboard.activeWorkers": "Active workers", "dashboard.checkingNow": "{count} checking now", "dashboard.availableStock": "Available stock", "dashboard.inCheckout": "{count} in checkout", "dashboard.successfulOrders": "Successful orders", "dashboard.successfulTasks": "{count} successful tasks", "dashboard.failedAttempts": "Failed attempts", "dashboard.failedTasks": "{count} failed tasks", "dashboard.taskFleet": "Task fleet", "dashboard.monitors": "Monitors at a glance", "dashboard.viewAll": "View all →", "dashboard.couldNotLoadTasks": "Could not load tasks.", "dashboard.noMonitors": "No monitors yet", "dashboard.createWatcher": "Create your first product watcher to start receiving availability signals.", "dashboard.createTask": "Create task", "dashboard.latestSignal": "Latest signal", "dashboard.systemHealth": "System health", "dashboard.apiService": "API service", "dashboard.workerManager": "Worker manager", "dashboard.browserSessions": "Browser sessions", "dashboard.latestError": "Latest error", "dashboard.operational": "Operational", "dashboard.needsAttention": "Needs attention", "dashboard.noRecentErrors": "No recent errors", "dashboard.loading": "Loading telemetry…",
  "tasks.eyebrow": "Automation / monitors", "tasks.title": "Tasks", "tasks.subtitle": "Run independent product watchers with one saved NOCIX account per task.", "tasks.add": "+ Add task", "tasks.loading": "Loading tasks…", "tasks.loadError": "Could not load tasks. Refresh the page and try again.", "tasks.emptyTitle": "Your task fleet is empty", "tasks.emptyBody": "Set a product ID, target price, and existing NOCIX account to begin.", "tasks.createFirst": "Create first task", "tasks.updated": "Task updated.", "tasks.created": "Task created.", "tasks.checkStarted": "Check started.", "tasks.started": "Monitor started.", "tasks.paused": "Task paused.", "tasks.resumed": "Task resumed.", "tasks.stopped": "Task stopped.", "tasks.actionFailed": "Action failed.", "tasks.savedError": "Could not save task.", "tasks.deleted": "Task deleted.", "tasks.deleteError": "Could not delete task.", "tasks.deleteConfirm": "Delete the monitor for product {product}? This removes its history.", "tasks.count": "{count} tasks",
  "orders.eyebrow": "Checkout outcomes", "orders.title": "Orders", "orders.subtitle": "A chronological record of submitted and blocked checkout attempts.", "orders.refresh": "↻ Refresh", "orders.clear": "Clear history", "orders.clearConfirm": "Clear all order history? This cannot be undone.", "orders.cleared": "Order history cleared.", "orders.clearError": "Could not clear order history.", "orders.loading": "Loading orders…", "orders.loadError": "Could not load orders.", "orders.status": "Status", "orders.taskProduct": "Task / product", "orders.observedPrice": "Observed price", "orders.targetPrice": "Target price", "orders.result": "Result", "orders.timestamp": "Timestamp", "orders.submitted": "Submitted", "orders.emptyTitle": "No order attempts", "orders.emptyBody": "Successful and failed checkout attempts will appear here.",
  "logs.eyebrow": "Runtime output", "logs.title": "Logs", "logs.subtitle": "Live worker events, redacted and capped at 500 rendered entries.", "logs.refresh": "↻ Refresh", "logs.clear": "Clear logs", "logs.clearConfirm": "Clear all logs? This cannot be undone.", "logs.cleared": "Logs cleared.", "logs.clearError": "Could not clear logs.", "logs.task": "Task", "logs.allTasks": "All tasks", "logs.level": "Level", "logs.allLevels": "All levels", "logs.polling": "Polling every 5s", "logs.loading": "Loading logs…", "logs.loadError": "Could not load logs.", "logs.system": "system", "logs.taskPrefix": "task {id}", "logs.noMatch": "No logs match", "logs.emptyBody": "Worker activity will show up here as tasks run.",
   "settings.eyebrow": "Service configuration", "settings.title": "Settings", "settings.subtitle": "Review runtime connectivity and update safe notification preferences.", "settings.loading": "Loading settings…", "settings.loadError": "Could not load settings.", "settings.runtime": "Runtime status", "settings.connections": "Service connections", "settings.apiAuth": "API authentication", "settings.browser": "Browser service", "settings.encryption": "Database encryption", "settings.telegram": "Telegram", "settings.proxy": "Proxy", "settings.payment": "Payment handling", "settings.notUsed": "not used by panel", "settings.notifications": "Notifications", "settings.delivery": "Telegram delivery", "settings.copy": "Only Telegram settings can be changed here. Secrets are sent to the backend and are never returned to the browser.", "settings.enableTelegram": "Enable Telegram notifications", "settings.notificationDetail": "Receive stock, checkout, and worker failure events.", "settings.enableProxy": "Enable global proxy", "settings.proxyDetail": "Tasks using “inherit” will use this proxy.", "settings.proxyUrl": "Proxy URL", "settings.replaceProxy": "Configured, enter to replace", "settings.enterProxy": "Enter proxy URL", "settings.proxyFormats": "Supports http:// and socks5:// formats with a host and port, without a query or fragment.", "settings.proxyStatus": "Proxy status: configured", "settings.testProxy": "Test proxy", "settings.proxyUrlInvalid": "Proxy URL must use http:// or socks5:// with a valid host and port, without a query or fragment.", "settings.proxyTestFailed": "Proxy test failed.", "settings.botToken": "Bot token", "settings.replaceToken": "Configured, enter to replace", "settings.pasteToken": "Paste Bot token", "settings.chatId": "Chat ID", "settings.replaceChat": "Configured, enter to replace", "settings.enterChat": "Enter Telegram Chat ID", "settings.save": "Save settings", "settings.saving": "Saving…", "settings.test": "Send test message", "settings.testing": "Testing…", "settings.saved": "Settings saved.", "settings.saveError": "Could not save Telegram settings.", "settings.testFailed": "Telegram test failed.", "settings.configured": "Configured", "settings.notConfigured": "Not configured", "settings.enabled": "Enabled", "settings.disabled": "Disabled",
  "task.editEyebrow": "Edit monitor", "task.newEyebrow": "New monitor", "task.editTitle": "Tune a task", "task.newTitle": "Watch a NOCIX product", "task.dialogDescription": "Configure a NOCIX product monitor and its saved account checkout settings.", "task.closeForm": "Close task form", "task.productId": "Product ID", "task.targetPrice": "Target price", "task.interval": "Check interval (seconds)", "task.operatingSystem": "Operating system", "task.email": "Existing NOCIX email", "task.password": "NOCIX password", "task.leaveUnchanged": "Leave unchanged", "task.stockUrl": "Stock URL", "task.cartUrl": "Cart URL", "task.optional": "optional", "task.derivedStock": "Derived from product ID when blank", "task.derivedCart": "Derived from product ID when blank", "task.paymentMethod": "Payment method: ", "task.paypalCopy": "Checkout uses PayPal already saved in NOCIX.", "task.autoSubmit": "Automatic submission enabled", "task.autoSubmitCopy": "Confirmed: submit once the target product and price match.", "task.cancel": "Cancel", "task.saving": "Saving…", "task.saveChanges": "Save changes", "task.create": "Create task", "task.productDigits": "Product ID must contain digits only.", "task.priceInvalid": "Target price must be a finite number greater than zero.", "task.intervalInvalid": "Check interval must be a finite whole number of at least 2 seconds.", "task.emailInvalid": "Enter a valid email address.", "task.accountRequired": "Existing NOCIX email and password are required.", "task.passwordRequired": "Existing NOCIX password is required for this task.", "task.stockUrlInvalid": "Stock URL must be valid HTTP(S) syntax on a NOCIX host.", "task.cartUrlInvalid": "Cart URL must be valid HTTP(S) syntax on a NOCIX host.", "task.target": "Target", "task.intervalShort": "Interval", "task.lastCheck": "Last check", "task.never": "Never", "task.confirmation": "Manual confirmation required.", "task.noRetry": "Cannot retry automatically.", "task.resume": "Resume", "task.pause": "Pause", "task.start": "Start monitor", "task.check": "Check now", "task.hideHistory": "Hide history", "task.history": "History", "task.edit": "Edit", "task.stop": "Stop", "task.delete": "Delete", "task.loadingHistory": "Loading history…", "task.historyError": "Could not load history.", "task.noPrice": "No price", "task.noAttempts": "No order attempts recorded.", "status.stopped": "Stopped", "status.running": "Running", "status.checking": "Checking", "status.ordering": "Ordering", "status.paused": "Paused", "status.success": "Success", "status.failed": "Failed", "status.unknown": "Unknown", "status.pending": "Pending confirmation",
};

translations["en-US"]["task.osDebian"] = "Debian";
translations["en-US"]["task.osUbuntu"] = "Ubuntu";
translations["en-US"]["settings.copy"] = "Only Telegram and proxy settings can be changed here. Secrets are sent to the backend and are never returned to the browser.";

translations["en-US"]["task.proxy"] = "Proxy";
translations["en-US"]["task.proxyMode"] = "Proxy mode";
translations["en-US"]["task.proxyInherit"] = "Use global proxy";
translations["en-US"]["task.proxyCustom"] = "Use custom proxy";
translations["en-US"]["task.proxyDirect"] = "Direct connection";
translations["en-US"]["task.customProxyUrl"] = "Custom proxy URL";
translations["en-US"]["task.proxyFormat"] = "http://host:port or socks5://user:password@host:port";
translations["en-US"]["task.proxyUrlInvalid"] = "Proxy URL must use http:// or socks5:// with a valid host and port, without a query or fragment.";

function readLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored === "en-US" || stored === "zh-CN" ? stored : "zh-CN";
  } catch {
    return "zh-CN";
  }
}

function interpolate(value: string, variables?: TranslationVariables): string {
  return value.replace(/\{(\w+)\}/g, (match, key: string) => variables?.[key] === undefined ? match : String(variables[key]));
}

interface I18nValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, variables?: TranslationVariables) => string;
}

const defaultTranslate = (key: string, variables?: TranslationVariables) => interpolate(translations["zh-CN"][key] ?? key, variables);
const I18nContext = createContext<I18nValue>({ language: "zh-CN", setLanguage: () => undefined, t: defaultTranslate });

export function I18nProvider({ children, initialLanguage }: { children: ReactNode; initialLanguage?: Language }) {
  const [language, setLanguageState] = useState<Language>(initialLanguage ?? readLanguage);
  const setLanguage = (next: Language) => {
    setLanguageState(next);
    try { window.localStorage.setItem(LANGUAGE_STORAGE_KEY, next); } catch { /* Storage can be unavailable in privacy modes. */ }
  };
  const t = (key: string, variables?: TranslationVariables) => {
    const value = translations[language][key] ?? translations["zh-CN"][key] ?? key;
    return interpolate(value, variables);
  };
  useEffect(() => {
    document.documentElement.lang = language;
    document.title = t("document.title");
  }, [language]);
  return <I18nContext.Provider value={{ language, setLanguage, t }}>{children}</I18nContext.Provider>;
}

export function useTranslation() {
  return useContext(I18nContext);
}
