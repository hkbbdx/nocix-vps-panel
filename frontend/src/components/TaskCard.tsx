import { useEffect, useRef, useState } from "react";
import { useLoginMutations, useLoginState, useTaskHistory } from "../hooks/use-tasks";
import type { Task } from "../lib/types";
import { StatusDot } from "./StatusDot";
import { useTranslation } from "../i18n";
import { EmailCodeDialog } from "./EmailCodeDialog";
import { ApiError, formatApiError } from "../lib/api";

interface TaskCardProps {
  task: Task;
  onAction: (action: "start" | "pause" | "resume" | "stop" | "check") => void;
  onEdit: (element: HTMLElement) => void;
  onDelete: () => void;
  busy?: boolean;
}

export function TaskCard({ task, onAction, onEdit, onDelete, busy = false }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [codeDialogOpen, setCodeDialogOpen] = useState(false);
  const [loginActionError, setLoginActionError] = useState("");
  const codeOpenerRef = useRef<HTMLButtonElement>(null);
  const history = useTaskHistory(expanded ? task.id : null);
  const loginState = useLoginState(task.id, task.status);
  const loginMutations = useLoginMutations();
  const { t } = useTranslation();
  const isActive = ["running", "checking", "ordering", "login_first", "login_second"].includes(task.status);
  const isSuccessful = task.status === "success";
  const isIndeterminate = ["unknown", "submitted_pending_confirmation"].includes(task.status);
  const canCheck = !isSuccessful && !isIndeterminate && !isActive && task.status !== "failed";
  const isLoginProgress = ["login_first", "login_second"].includes(task.status);
  const isWaitingForCode = task.status === "waiting_for_email_code";
  const loginStateIsTerminalError = loginState.error instanceof ApiError && loginState.error.status === 409;
  const liveWaitingForCode = isWaitingForCode && !loginStateIsTerminalError && (!loginState.data && !loginState.error || Boolean(loginState.data?.waiting && loginState.data.status === "waiting_for_email_code"));
  const loginStateTerminal = isWaitingForCode && !liveWaitingForCode && Boolean(loginState.data || loginState.error);
  const loginError = loginActionError || loginState.data?.last_error || (loginState.error ? formatApiError(loginState.error, t, "login.stateFailed") : "");

  useEffect(() => {
    if (!liveWaitingForCode) setCodeDialogOpen(false);
  }, [liveWaitingForCode]);

  const submitCode = async (code: string) => {
    setLoginActionError("");
    await loginMutations.submitEmailCode.mutateAsync({ id: task.id, code });
    setCodeDialogOpen(false);
  };

  const cancelLogin = async () => {
    setLoginActionError("");
    try {
      await loginMutations.cancelLogin.mutateAsync(task.id);
    } catch (error) {
      setLoginActionError(formatApiError(error, t, "login.cancelFailed"));
    }
  };

  return (
    <article className="task-panel">
      <div className="task-panel-head"><div className="task-identity"><span className="task-number">#{task.goods_id}</span><div><h3>{t("task.productId")} {task.goods_id}</h3><p>{task.email}</p></div></div><StatusDot status={task.status} /></div>
      <div className="task-metrics"><div><span>{t("task.target")}</span><strong>${task.target_price.toFixed(2)}</strong></div><div><span>{t("task.intervalShort")}</span><strong>{task.wait_interval}s</strong></div><div><span>{t("task.operatingSystem")}</span><strong>{task.operating_system}</strong></div><div><span>{t("task.proxy")}</span><strong>{(task.proxy_mode === "direct" ? false : task.proxy_mode === "custom" ? task.proxy_configured : task.effective_proxy_configured) ? t("settings.configured") : t("settings.notConfigured")}</strong></div><div><span>{t("task.lastCheck")}</span><strong>{task.last_checked_at ? new Date(task.last_checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : t("task.never")}</strong></div></div>
      {isLoginProgress && <div className="task-alert task-alert-warning" role="status"><span>!</span><div>{t(task.status === "login_first" ? "login.progressFirst" : "login.progressSecond")}</div></div>}
      {liveWaitingForCode && <div className="task-alert task-alert-warning" role="status"><span>!</span><div><strong>{t("login.waiting")}</strong><div>{t("login.attempts", { count: loginState.data?.attempts ?? 0 })} · {t("login.remaining", { seconds: loginState.data?.remaining_seconds ?? 0 })}</div></div></div>}
      {isIndeterminate && <div className="task-alert task-alert-warning" role="alert"><span>!</span><div><strong>{t("task.confirmation")}</strong> {t("task.noRetry")}</div></div>}
      {isWaitingForCode && loginError && <div className="task-alert" role="alert"><span>!</span>{loginError}</div>}
      {task.last_error && !isIndeterminate && !isWaitingForCode && !isLoginProgress && <div className="task-alert"><span>!</span>{task.last_error}</div>}
      <div className="task-panel-actions">
        {liveWaitingForCode ? <>
          <button ref={codeOpenerRef} className="button-primary button-small" disabled={busy || loginMutations.cancelLogin.isPending} onClick={() => setCodeDialogOpen(true)}>{t("login.enterCode")}</button>
          <button className="button-danger button-small" disabled={busy || loginMutations.cancelLogin.isPending} onClick={() => void cancelLogin()}>{t("login.cancelLogin")}</button>
        </> : loginStateTerminal ? null : <>
          {!isSuccessful && !isIndeterminate && (task.status === "paused" ? <button className="button-primary button-small" disabled={busy} onClick={() => onAction("resume")}>{t("task.resume")}</button> : isActive ? <button className="button-secondary button-small" disabled={busy} onClick={() => onAction("pause")}>{t("task.pause")}</button> : <button className="button-primary button-small" disabled={busy} onClick={() => onAction("start")}>{t("task.start")}</button>)}
          {canCheck && <button className="button-secondary button-small" disabled={busy} onClick={() => onAction("check")}>{t("task.check")}</button>}
          <button className="button-quiet button-small" disabled={busy} onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>{expanded ? t("task.hideHistory") : t("task.history")}</button>
          {!isSuccessful && !isActive && <button className="button-quiet button-small" disabled={busy || isIndeterminate} onClick={(event) => onEdit(event.currentTarget)}>{t("task.edit")}</button>}
          {isActive && <button className="button-danger button-small" disabled={busy} onClick={() => onAction("stop")}>{t("task.stop")}</button>}
          {!isLoginProgress && <button className="button-quiet button-small" disabled={busy} onClick={onDelete}>{t("task.delete")}</button>}
        </>}
      </div>
      {expanded && <div className="history-panel">{history.isLoading ? <p className="muted">{t("task.loadingHistory")}</p> : history.error ? <p className="form-error" role="alert">{t("task.historyError")}</p> : history.data?.length ? history.data.map((entry) => <div className="history-row" key={entry.id}><StatusDot status={entry.status} /><span>{entry.observed_price ?? t("task.noPrice")}</span><time>{new Date(entry.created_at).toLocaleString()}</time><span>{entry.error ?? ""}</span></div>) : <p className="muted">{t("task.noAttempts")}</p>}</div>}
      {liveWaitingForCode && codeDialogOpen && <div className="modal-backdrop"><EmailCodeDialog restoreFocusRef={codeOpenerRef} busy={loginMutations.submitEmailCode.isPending || loginMutations.cancelLogin.isPending} onSubmit={submitCode} onCancel={() => setCodeDialogOpen(false)} /></div>}
    </article>
  );
}
