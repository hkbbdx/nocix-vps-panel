import { useCallback, useEffect, useRef, useState } from "react";
import { TaskCard } from "../components/TaskCard";
import { TaskDialog } from "../components/TaskDialog";
import { useTaskMutations, useTasks } from "../hooks/use-tasks";
import type { Task, TaskInput } from "../lib/types";

export function Tasks() {
  const query = useTasks();
  const mutations = useTaskMutations();
  const [editing, setEditing] = useState<Task | null | undefined>(undefined);
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const noticeTimer = useRef<number | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const busy = mutations.create.isPending || mutations.update.isPending || mutations.remove.isPending || mutations.action.isPending;
  const show = useCallback((message: string, isError = false) => {
    if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current);
    setNotice(message);
    setNoticeError(isError);
    noticeTimer.current = window.setTimeout(() => { setNotice(""); noticeTimer.current = null; }, 3500);
  }, []);
  useEffect(() => () => { if (noticeTimer.current !== null) window.clearTimeout(noticeTimer.current); }, []);
  const submit = async (input: TaskInput | Partial<TaskInput>) => { try { if (editing) { await mutations.update.mutateAsync({ id: editing.id, input }); show("Task updated."); } else { await mutations.create.mutateAsync(input as TaskInput); show("Task created."); } setEditing(undefined); } catch (error) { show(error instanceof Error ? error.message : "Could not save task.", true); } };
  const action = async (task: Task, actionName: "start" | "pause" | "resume" | "stop" | "check") => { try { await mutations.action.mutateAsync({ id: task.id, action: actionName }); show(`${actionName === "check" ? "Check started" : `Task ${actionName}ed`}.`); } catch (error) { show(error instanceof Error ? error.message : "Action failed.", true); } };
  const remove = async (task: Task) => { if (!window.confirm(`Delete the monitor for product ${task.goods_id}? This removes its history.`)) return; try { await mutations.remove.mutateAsync(task.id); show("Task deleted."); } catch (error) { show(error instanceof Error ? error.message : "Could not delete task.", true); } };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Automation / monitors</p><h1>Tasks</h1><p className="page-subtitle">Run independent product watchers with one saved NOCIX account per task.</p></div><button className="button-primary" onClick={(event) => { openerRef.current = event.currentTarget; setEditing(null); }}>+ Add task</button></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}{query.isLoading ? <div className="panel loading-block">Loading tasks…</div> : query.error ? <div className="panel inline-error" role="alert">Could not load tasks. Refresh the page and try again.</div> : query.data?.length ? <div className="task-list">{query.data.map((task) => <TaskCard key={task.id} task={task} busy={busy} onAction={(actionName) => void action(task, actionName)} onEdit={(element) => { openerRef.current = element; setEditing(task); }} onDelete={() => void remove(task)} />)}</div> : <div className="panel empty-state large"><span className="empty-mark">＋</span><strong>Your task fleet is empty</strong><p>Set a product ID, target price, and existing NOCIX account to begin.</p><button className="button-primary" onClick={(event) => { openerRef.current = event.currentTarget; setEditing(null); }}>Create first task</button></div>}{editing !== undefined && <div className="modal-backdrop"><TaskDialog task={editing} restoreFocusRef={openerRef} busy={busy} onSubmit={submit} onClose={() => setEditing(undefined)} /></div>}</div>;
}
