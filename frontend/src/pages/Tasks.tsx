import { useCallback, useEffect, useRef, useState } from "react";
import { TaskCard } from "../components/TaskCard";
import { TaskDialog } from "../components/TaskDialog";
import { useTaskMutations, useTasks } from "../hooks/use-tasks";
import type { Task, TaskInput } from "../lib/types";
import { useTranslation } from "../i18n";
import { formatApiError } from "../lib/api";

export function Tasks() {
  const query = useTasks();
  const mutations = useTaskMutations();
  const [editing, setEditing] = useState<Task | null | undefined>(undefined);
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const noticeTimer = useRef<number | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const busy = mutations.create.isPending || mutations.update.isPending || mutations.remove.isPending || mutations.action.isPending;
  const { t } = useTranslation();
  const show = useCallback((message: string, isError = false) => {
    if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current);
    setNotice(message);
    setNoticeError(isError);
    noticeTimer.current = window.setTimeout(() => { setNotice(""); noticeTimer.current = null; }, 3500);
  }, []);
  useEffect(() => () => { if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current); }, []);
  const submit = async (input: TaskInput | Partial<TaskInput>) => { try { if (editing) { await mutations.update.mutateAsync({ id: editing.id, input }); show(t("tasks.updated")); } else { await mutations.create.mutateAsync(input as TaskInput); show(t("tasks.created")); } setEditing(undefined); } catch (error) { show(formatApiError(error, t, "tasks.savedError"), true); } };
  const action = async (task: Task, actionName: "start" | "pause" | "resume" | "stop" | "check") => { try { await mutations.action.mutateAsync({ id: task.id, action: actionName }); show(t(getTaskActionFeedbackKey(actionName))); } catch (error) { show(formatApiError(error, t, "tasks.actionFailed"), true); } };
  const remove = async (task: Task) => { if (!window.confirm(t("tasks.deleteConfirm", { product: task.goods_id }))) return; try { await mutations.remove.mutateAsync(task.id); show(t("tasks.deleted")); } catch (error) { show(formatApiError(error, t, "tasks.deleteError"), true); } };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">{t("tasks.eyebrow")}</p><h1>{t("tasks.title")}</h1><p className="page-subtitle">{t("tasks.subtitle")}</p></div><button className="button-primary" onClick={(event) => { openerRef.current = event.currentTarget; setEditing(null); }}>{t("tasks.add")}</button></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}{query.isLoading ? <div className="panel loading-block">{t("tasks.loading")}</div> : query.error ? <div className="panel inline-error" role="alert">{t("tasks.loadError")}</div> : query.data?.length ? <div className="task-list">{query.data.map((task) => <TaskCard key={task.id} task={task} busy={busy} onAction={(actionName) => void action(task, actionName)} onEdit={(element) => { openerRef.current = element; setEditing(task); }} onDelete={() => void remove(task)} />)}</div> : <div className="panel empty-state large"><span className="empty-mark">＋</span><strong>{t("tasks.emptyTitle")}</strong><p>{t("tasks.emptyBody")}</p><button className="button-primary" onClick={(event) => { openerRef.current = event.currentTarget; setEditing(null); }}>{t("tasks.createFirst")}</button></div>}{editing !== undefined && <div className="modal-backdrop"><TaskDialog task={editing} restoreFocusRef={openerRef} busy={busy} onSubmit={submit} onClose={() => setEditing(undefined)} /></div>}</div>;
}

export function getTaskActionFeedbackKey(action: "start" | "pause" | "resume" | "stop" | "check") {
  return { start: "tasks.started", pause: "tasks.paused", resume: "tasks.resumed", stop: "tasks.stopped", check: "tasks.checkStarted" }[action];
}
