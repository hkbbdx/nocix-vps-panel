export type TaskStatus =
  | "stopped"
  | "running"
  | "checking"
  | "ordering"
  | "paused"
  | "success"
   | "failed"
   | "unknown"
   | "submitted_pending_confirmation"
   | "login_first"
   | "login_second"
   | "waiting_for_email_code";

export type ProxyMode = "inherit" | "custom" | "direct";

export interface Task {
  id: string;
  goods_id: string;
  stock_url: string;
  cart_url: string;
  target_price: number;
  wait_interval: number;
  operating_system: "debian" | "ubuntu";
  email: string;
  new_customer: false;
  payment_method: "paypal";
  auto_submit: boolean;
  proxy_mode: ProxyMode;
  proxy_configured: boolean;
  effective_proxy_configured: boolean;
  password_configured: boolean;
  status: TaskStatus;
  last_stock_status: string | null;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface TaskInput {
  goods_id: string;
  stock_url?: string;
  cart_url?: string;
  target_price: number;
  wait_interval: number;
  operating_system: "debian" | "ubuntu";
  email: string;
  password?: string;
  new_customer: false;
  payment_method: "paypal";
  auto_submit: true;
  proxy_mode: ProxyMode;
  proxy_url?: string | null;
}

export interface Order {
  id: number;
  task_id: string;
  status: "success" | "failed" | "unknown" | string;
  observed_price: string | null;
  error: string | null;
  created_at: string;
}

export interface LogEntry {
  id: number;
  level: string;
  task_id: string | null;
  message: string;
  created_at: string;
}

export interface Stats {
  worker_count: number;
  task_count: number;
  available_count: number;
  checking_count: number;
  ordering_count: number;
  success_count: number;
  failure_count: number;
  order_success_count: number;
  order_failure_count: number;
  last_error: string | null;
}

export interface RuntimeSettings {
  environment: string;
  browser_configured: boolean;
  api_key_configured: boolean;
  encryption_key_configured: boolean;
  telegram_enabled: boolean;
  telegram_configured: boolean;
  log_level: string;
  proxy_enabled: boolean;
  proxy_configured: boolean;
  proxy_display?: string;
}

export interface SettingsUpdate {
  log_level?: string;
  telegram_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  proxy_enabled?: boolean;
  proxy_url?: string | null;
}

export interface ProxyTestResult {
  success: boolean;
  proxy: "direct" | string;
  message: string;
}

export interface TaskHistoryEntry extends Order {
  [key: string]: unknown;
}

export interface LoginState {
  task_id: string;
  status: TaskStatus;
  waiting: boolean;
  attempts: number;
  remaining_seconds: number;
  last_error: string | null;
}

export interface LoginActionResult extends LoginState {
  result: "accepted" | "rejected" | "cancelled";
  message: string;
}
