import { Link } from "react-router-dom";
import { useDashboard } from "../hooks/use-dashboard";
import { useTasks } from "../hooks/use-tasks";
import { StatusDot } from "../components/StatusDot";
import { useTranslation } from "../i18n";
import { recentUpdates } from "../lib/updates";
import { UpdateCard } from "./Updates";

export function Dashboard() {
  const stats = useDashboard();
  const tasks = useTasks();
  const data = stats.data;
  const { language, t } = useTranslation();
  return <div className="page-stack">
    <div className="page-heading"><div><p className="eyebrow">{t("dashboard.eyebrow")}</p><h1>{t("dashboard.title")}</h1><p className="page-subtitle">{t("dashboard.subtitle")}</p></div><Link className="button-primary" to="/tasks">{t("dashboard.newTask")}</Link></div>
    {stats.error && <div className="inline-error" role="alert">{t("dashboard.statsUnavailable")}</div>}
    <div className="metric-grid"><Metric label={t("dashboard.activeWorkers")} value={data?.worker_count ?? "—"} note={t("dashboard.checkingNow", { count: data?.checking_count ?? 0 })} accent="cyan" /><Metric label={t("dashboard.availableStock")} value={data?.available_count ?? "—"} note={t("dashboard.inCheckout", { count: data?.ordering_count ?? 0 })} accent="green" /><Metric label={t("dashboard.successfulOrders")} value={data?.order_success_count ?? "—"} note={t("dashboard.successfulTasks", { count: data?.success_count ?? 0 })} accent="violet" /><Metric label={t("dashboard.failedAttempts")} value={data?.order_failure_count ?? "—"} note={t("dashboard.failedTasks", { count: data?.failure_count ?? 0 })} accent="amber" /></div>
    <div className="dashboard-grid"><section className="panel activity-panel"><div className="panel-heading"><div><p className="eyebrow">{t("dashboard.taskFleet")}</p><h2>{t("dashboard.monitors")}</h2></div><Link to="/tasks" className="text-link">{t("dashboard.viewAll")}</Link></div>{tasks.isLoading ? <Loading /> : tasks.error ? <div className="inline-error" role="alert">{t("dashboard.couldNotLoadTasks")}</div> : tasks.data?.length ? <div className="mini-task-list">{tasks.data.slice(0, 4).map((task) => <div className="mini-task" key={task.id}><div className="mini-task-title"><span className="task-number">#{task.goods_id}</span><strong>{t("task.productId")} {task.goods_id}</strong></div><StatusDot status={task.status} /><span className="mini-price">≤ ${task.target_price.toFixed(2)}</span></div>)}</div> : <Empty title={t("dashboard.noMonitors")} body={t("dashboard.createWatcher")} action={t("dashboard.createTask")} />}</section><section className="panel signal-panel"><div className="panel-heading"><div><p className="eyebrow">{t("dashboard.latestSignal")}</p><h2>{t("dashboard.systemHealth")}</h2></div><span className="signal-ring">✓</span></div><div className="health-list"><HealthRow label={t("dashboard.apiService")} good /><HealthRow label={t("dashboard.workerManager")} good /><HealthRow label={t("dashboard.browserSessions")} good={Boolean(data)} /><HealthRow label={t("dashboard.latestError")} good={!data?.last_error} detail={data?.last_error ?? t("dashboard.noRecentErrors")} /></div></section></div>
    <section className="panel recent-updates-panel" aria-labelledby="recent-updates-title"><div className="panel-heading"><div><p className="eyebrow">{t("updates.eyebrow")}</p><h2 id="recent-updates-title">{t("updates.recent")}</h2></div><Link to="/updates" className="text-link">{t("updates.viewAll")}</Link></div><div className="updates-list updates-list-recent">{recentUpdates().map((entry) => <UpdateCard key={entry.commit} entry={entry} language={language} t={t} compact />)}</div></section>
  </div>;
}

function Metric({ label, value, note, accent }: { label: string; value: string | number; note: string; accent: string }) { return <div className={`metric-panel metric-${accent}`}><span className="metric-label">{label}</span><strong>{value}</strong><span className="metric-note">{note}</span></div>; }
function HealthRow({ label, good, detail }: { label: string; good: boolean; detail?: string }) { const { t } = useTranslation(); return <div className="health-row"><span className={`status-dot ${good ? "status-dot-good" : "status-dot-bad"}`} /><div><strong>{label}</strong><span>{detail ?? (good ? t("dashboard.operational") : t("dashboard.needsAttention"))}</span></div></div>; }
function Loading() { const { t } = useTranslation(); return <div className="loading-block">{t("dashboard.loading")}</div>; }
function Empty({ title, body, action }: { title: string; body: string; action: string }) { return <div className="empty-state"><span className="empty-mark">＋</span><strong>{title}</strong><p>{body}</p><Link className="button-secondary button-small" to="/tasks">{action}</Link></div>; }
