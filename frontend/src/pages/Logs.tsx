import { useEffect, useState } from "react";
import { useClearLogs, useLogs } from "../hooks/use-logs";
import { useTasks } from "../hooks/use-tasks";
import { useTranslation } from "../i18n";
import { formatApiError } from "../lib/api";

export function Logs() {
  const [taskId, setTaskId] = useState("");
  const [level, setLevel] = useState("");
  const [visible, setVisible] = useState(true);
  const query = useLogs(taskId || undefined, level || undefined, visible);
  const tasks = useTasks();
  const clear = useClearLogs();
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const { t } = useTranslation();
  useEffect(() => { const onVisibility = () => setVisible(document.visibilityState === "visible"); document.addEventListener("visibilitychange", onVisibility); return () => document.removeEventListener("visibilitychange", onVisibility); }, []);
  const clearAll = () => { if (!window.confirm(t("logs.clearConfirm"))) return; clear.mutate(undefined, { onSuccess: () => { setNoticeError(false); setNotice(t("logs.cleared")); }, onError: (error) => { setNoticeError(true); setNotice(formatApiError(error, t, "logs.clearError")); } }); };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">{t("logs.eyebrow")}</p><h1>{t("logs.title")}</h1><p className="page-subtitle">{t("logs.subtitle")}</p></div><div className="heading-actions"><button className="button-secondary" onClick={() => void query.refetch()}>{t("logs.refresh")}</button><button className="button-danger" onClick={clearAll} disabled={clear.isPending}>{t("logs.clear")}</button></div></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}<section className="panel logs-panel"><div className="filter-bar"><label>{t("logs.task")}<select value={taskId} onChange={(event) => setTaskId(event.target.value)}><option value="">{t("logs.allTasks")}</option>{tasks.data?.map((task) => <option key={task.id} value={task.id}>{t("task.productId")} {task.goods_id}</option>)}</select></label><label>{t("logs.level")}<select value={level} onChange={(event) => setLevel(event.target.value)}><option value="">{t("logs.allLevels")}</option><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select></label><span className="log-live"><span className="status-dot status-dot-good" /> {t("logs.polling")}</span></div>{query.isLoading ? <div className="loading-block">{t("logs.loading")}</div> : query.error ? <div className="inline-error" role="alert">{t("logs.loadError")}</div> : query.data?.length ? <div className="log-list">{query.data.slice(0, 500).map((entry) => <div className="log-row" key={entry.id}><time>{new Date(entry.created_at).toLocaleTimeString()}</time><span className={`level level-${entry.level.toLowerCase()}`}>{entry.level}</span><span className="log-task">{entry.task_id ? t("logs.taskPrefix", { id: entry.task_id.slice(0, 8) }) : t("logs.system")}</span><p>{entry.message}</p></div>)}</div> : <div className="empty-state"><span className="empty-mark">≡</span><strong>{t("logs.noMatch")}</strong><p>{t("logs.emptyBody")}</p></div>}</section></div>;
}
