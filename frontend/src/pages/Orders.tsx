import { useState } from "react";
import { useClearOrders, useOrders } from "../hooks/use-orders";
import { useTasks } from "../hooks/use-tasks";
import { StatusDot } from "../components/StatusDot";

export function Orders() {
  const query = useOrders();
  const tasks = useTasks();
  const clear = useClearOrders();
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const taskName = (id: string) => tasks.data?.find((task) => task.id === id)?.goods_id ?? id.slice(0, 8);
  const clearAll = () => { if (!window.confirm("Clear all order history? This cannot be undone.")) return; clear.mutate(undefined, { onSuccess: () => { setNoticeError(false); setNotice("Order history cleared."); }, onError: (error) => { setNoticeError(true); setNotice(error instanceof Error ? error.message : "Could not clear order history."); } }); };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Checkout outcomes</p><h1>Orders</h1><p className="page-subtitle">A chronological record of submitted and blocked checkout attempts.</p></div><div className="heading-actions"><button className="button-secondary" onClick={() => void query.refetch()}>↻ Refresh</button><button className="button-danger" onClick={clearAll} disabled={clear.isPending}>Clear history</button></div></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}<section className="panel table-panel">{query.isLoading ? <div className="loading-block">Loading orders…</div> : query.error ? <div className="inline-error" role="alert">Could not load orders.</div> : query.data?.length ? <div className="table-scroll"><table><thead><tr><th>Status</th><th>Task / product</th><th>Observed price</th><th>Target price</th><th>Result</th><th>Timestamp</th></tr></thead><tbody>{query.data.map((order) => { const task = tasks.data?.find((item) => item.id === order.task_id); return <tr key={order.id}><td><StatusDot status={order.status} /></td><td><strong>Product {taskName(order.task_id)}</strong><small>{order.task_id}</small></td><td>{order.observed_price ?? "—"}</td><td>{task ? `$${task.target_price.toFixed(2)}` : "—"}</td><td className={order.error ? "text-danger" : "text-success"}>{order.error ?? "Submitted"}</td><td>{new Date(order.created_at).toLocaleString()}</td></tr>; })}</tbody></table></div> : <div className="empty-state"><span className="empty-mark">↗</span><strong>No order attempts</strong><p>Successful and failed checkout attempts will appear here.</p></div>}</section></div>;
}
