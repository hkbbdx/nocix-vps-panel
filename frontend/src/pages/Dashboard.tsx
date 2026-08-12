import { Link } from "react-router-dom";
import { useDashboard } from "../hooks/use-dashboard";
import { useTasks } from "../hooks/use-tasks";
import { StatusDot } from "../components/StatusDot";

export function Dashboard() {
  const stats = useDashboard();
  const tasks = useTasks();
  const data = stats.data;
  return <div className="page-stack">
    <div className="page-heading"><div><p className="eyebrow">Tuesday, August 11 / worker telemetry</p><h1>Overview</h1><p className="page-subtitle">A live read on your NOCIX availability monitors and checkout queue.</p></div><Link className="button-primary" to="/tasks">+ New task</Link></div>
    {stats.error && <div className="inline-error" role="alert">Stats unavailable. Check the API connection and refresh.</div>}
    <div className="metric-grid"><Metric label="Active workers" value={data?.worker_count ?? "—"} note={`${data?.checking_count ?? 0} checking now`} accent="cyan" /><Metric label="Available stock" value={data?.available_count ?? "—"} note={`${data?.ordering_count ?? 0} in checkout`} accent="green" /><Metric label="Successful orders" value={data?.order_success_count ?? "—"} note={`${data?.success_count ?? 0} successful tasks`} accent="violet" /><Metric label="Failed attempts" value={data?.order_failure_count ?? "—"} note={`${data?.failure_count ?? 0} failed tasks`} accent="amber" /></div>
    <div className="dashboard-grid"><section className="panel activity-panel"><div className="panel-heading"><div><p className="eyebrow">Task fleet</p><h2>Monitors at a glance</h2></div><Link to="/tasks" className="text-link">View all →</Link></div>{tasks.isLoading ? <Loading /> : tasks.error ? <div className="inline-error" role="alert">Could not load tasks.</div> : tasks.data?.length ? <div className="mini-task-list">{tasks.data.slice(0, 4).map((task) => <div className="mini-task" key={task.id}><div className="mini-task-title"><span className="task-number">#{task.goods_id}</span><strong>Product {task.goods_id}</strong></div><StatusDot status={task.status} /><span className="mini-price">≤ ${task.target_price.toFixed(2)}</span></div>)}</div> : <Empty title="No monitors yet" body="Create your first product watcher to start receiving availability signals." action="Create task" />}</section><section className="panel signal-panel"><div className="panel-heading"><div><p className="eyebrow">Latest signal</p><h2>System health</h2></div><span className="signal-ring">✓</span></div><div className="health-list"><HealthRow label="API service" good /><HealthRow label="Worker manager" good /><HealthRow label="Browser sessions" good={Boolean(data)} /><HealthRow label="Latest error" good={!data?.last_error} detail={data?.last_error ?? "No recent errors"} /></div></section></div>
  </div>;
}

function Metric({ label, value, note, accent }: { label: string; value: string | number; note: string; accent: string }) { return <div className={`metric-panel metric-${accent}`}><span className="metric-label">{label}</span><strong>{value}</strong><span className="metric-note">{note}</span></div>; }
function HealthRow({ label, good, detail }: { label: string; good: boolean; detail?: string }) { return <div className="health-row"><span className={`status-dot ${good ? "status-dot-good" : "status-dot-bad"}`} /><div><strong>{label}</strong><span>{detail ?? (good ? "Operational" : "Needs attention")}</span></div></div>; }
function Loading() { return <div className="loading-block">Loading telemetry…</div>; }
function Empty({ title, body, action }: { title: string; body: string; action: string }) { return <div className="empty-state"><span className="empty-mark">＋</span><strong>{title}</strong><p>{body}</p><Link className="button-secondary button-small" to="/tasks">{action}</Link></div>; }
