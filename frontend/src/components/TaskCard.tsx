import { useState } from "react";
import { useTaskHistory } from "../hooks/use-tasks";
import type { Task } from "../lib/types";
import { StatusDot } from "./StatusDot";
import { useTranslation } from "../i18n";

interface TaskCardProps {
  task: Task;
  onAction: (action: "start" | "pause" | "resume" | "stop" | "check") => void;
  onEdit: (element: HTMLElement) => void;
  onDelete: () => void;
  busy?: boolean;
}

export function TaskCard({ task, onAction, onEdit, onDelete, busy = false }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const history = useTaskHistory(expanded ? task.id : null);
  const { t } = useTranslation();
  const isActive = ["running", "checking", "ordering"].includes(task.status);
  const isSuccessful = task.status === "success";
  const isIndeterminate = ["unknown", "submitted_pending_confirmation"].includes(task.status);
  const canCheck = !isSuccessful && !isIndeterminate && !isActive && task.status !== "failed";

  return (
    <article className="task-panel">
      <div className="task-panel-head"><div className="task-identity"><span className="task-number">#{task.goods_id}</span><div><h3>{t("task.productId")} {task.goods_id}</h3><p>{task.email}</p></div></div><StatusDot status={task.status} /></div>
      <div className="task-metrics"><div><span>{t("task.target")}</span><strong>${task.target_price.toFixed(2)}</strong></div><div><span>{t("task.intervalShort")}</span><strong>{task.wait_interval}s</strong></div><div><span>{t("task.operatingSystem")}</span><strong>{task.operating_system}</strong></div><div><span>{t("task.lastCheck")}</span><strong>{task.last_checked_at ? new Date(task.last_checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : t("task.never")}</strong></div></div>
       {isIndeterminate && <div className="task-alert task-alert-warning" role="alert"><span>!</span><div><strong>{t("task.confirmation")}</strong> {t("task.noRetry")}</div></div>}
       {task.last_error && !isIndeterminate && <div className="task-alert"><span>!</span>{task.last_error}</div>}
       <div className="task-panel-actions">
           {!isSuccessful && !isIndeterminate && (task.status === "paused" ? <button className="button-primary button-small" disabled={busy} onClick={() => onAction("resume")}>{t("task.resume")}</button> : isActive ? <button className="button-secondary button-small" disabled={busy} onClick={() => onAction("pause")}>{t("task.pause")}</button> : <button className="button-primary button-small" disabled={busy} onClick={() => onAction("start")}>{t("task.start")}</button>)}
           {canCheck && <button className="button-secondary button-small" disabled={busy} onClick={() => onAction("check")}>{t("task.check")}</button>}
          <button className="button-quiet button-small" disabled={busy} onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>{expanded ? t("task.hideHistory") : t("task.history")}</button>
            {!isSuccessful && !isActive && <button className="button-quiet button-small" disabled={busy || isIndeterminate} onClick={(event) => onEdit(event.currentTarget)}>{t("task.edit")}</button>}
          {isActive && <button className="button-danger button-small" disabled={busy} onClick={() => onAction("stop")}>{t("task.stop")}</button>}
          <button className="button-quiet button-small" disabled={busy} onClick={onDelete}>{t("task.delete")}</button>
       </div>
        {expanded && <div className="history-panel">{history.isLoading ? <p className="muted">{t("task.loadingHistory")}</p> : history.error ? <p className="form-error" role="alert">{t("task.historyError")}</p> : history.data?.length ? history.data.map((entry) => <div className="history-row" key={entry.id}><StatusDot status={entry.status} /><span>{entry.observed_price ?? t("task.noPrice")}</span><time>{new Date(entry.created_at).toLocaleString()}</time><span>{entry.error ?? ""}</span></div>) : <p className="muted">{t("task.noAttempts")}</p>}</div>}
    </article>
  );
}
