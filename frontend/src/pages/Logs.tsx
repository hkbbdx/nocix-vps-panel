import { useEffect, useState } from "react";
import { useClearLogs, useLogs } from "../hooks/use-logs";
import { useTasks } from "../hooks/use-tasks";

export function Logs() {
  const [taskId, setTaskId] = useState("");
  const [level, setLevel] = useState("");
  const [visible, setVisible] = useState(true);
  const query = useLogs(taskId || undefined, level || undefined, visible);
  const tasks = useTasks();
  const clear = useClearLogs();
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  useEffect(() => { const onVisibility = () => setVisible(document.visibilityState === "visible"); document.addEventListener("visibilitychange", onVisibility); return () => document.removeEventListener("visibilitychange", onVisibility); }, []);
  const clearAll = () => { if (!window.confirm("Clear all logs? This cannot be undone.")) return; clear.mutate(undefined, { onSuccess: () => { setNoticeError(false); setNotice("Logs cleared."); }, onError: (error) => { setNoticeError(true); setNotice(error instanceof Error ? error.message : "Could not clear logs."); } }); };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Runtime output</p><h1>Logs</h1><p className="page-subtitle">Live worker events, redacted and capped at 500 rendered entries.</p></div><div className="heading-actions"><button className="button-secondary" onClick={() => void query.refetch()}>↻ Refresh</button><button className="button-danger" onClick={clearAll} disabled={clear.isPending}>Clear logs</button></div></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}<section className="panel logs-panel"><div className="filter-bar"><label>Task<select value={taskId} onChange={(event) => setTaskId(event.target.value)}><option value="">All tasks</option>{tasks.data?.map((task) => <option key={task.id} value={task.id}>Product {task.goods_id}</option>)}</select></label><label>Level<select value={level} onChange={(event) => setLevel(event.target.value)}><option value="">All levels</option><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select></label><span className="log-live"><span className="status-dot status-dot-good" /> Polling every 5s</span></div>{query.isLoading ? <div className="loading-block">Loading logs…</div> : query.error ? <div className="inline-error" role="alert">Could not load logs.</div> : query.data?.length ? <div className="log-list">{query.data.slice(0, 500).map((entry) => <div className="log-row" key={entry.id}><time>{new Date(entry.created_at).toLocaleTimeString()}</time><span className={`level level-${entry.level.toLowerCase()}`}>{entry.level}</span><span className="log-task">{entry.task_id ? `task ${entry.task_id.slice(0, 8)}` : "system"}</span><p>{entry.message}</p></div>)}</div> : <div className="empty-state"><span className="empty-mark">≡</span><strong>No logs match</strong><p>Worker activity will show up here as tasks run.</p></div>}</section></div>;
}
