import { useState } from "react";
import { useClearOrders, useOrders } from "../hooks/use-orders";
import { useTasks } from "../hooks/use-tasks";
import { StatusDot } from "../components/StatusDot";
import { useTranslation } from "../i18n";
import { formatApiError } from "../lib/api";

export function Orders() {
  const query = useOrders();
  const tasks = useTasks();
  const clear = useClearOrders();
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const { t } = useTranslation();
  const taskName = (id: string) => tasks.data?.find((task) => task.id === id)?.goods_id ?? id.slice(0, 8);
  const clearAll = () => { if (!window.confirm(t("orders.clearConfirm"))) return; clear.mutate(undefined, { onSuccess: () => { setNoticeError(false); setNotice(t("orders.cleared")); }, onError: (error) => { setNoticeError(true); setNotice(formatApiError(error, t, "orders.clearError")); } }); };
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">{t("orders.eyebrow")}</p><h1>{t("orders.title")}</h1><p className="page-subtitle">{t("orders.subtitle")}</p></div><div className="heading-actions"><button className="button-secondary" onClick={() => void query.refetch()}>{t("orders.refresh")}</button><button className="button-danger" onClick={clearAll} disabled={clear.isPending}>{t("orders.clear")}</button></div></div>{notice && <div className={`toast ${noticeError ? "toast-error" : ""}`} role={noticeError ? "alert" : "status"}>{notice}</div>}<section className="panel table-panel">{query.isLoading ? <div className="loading-block">{t("orders.loading")}</div> : query.error ? <div className="inline-error" role="alert">{t("orders.loadError")}</div> : query.data?.length ? <div className="table-scroll"><table><thead><tr><th>{t("orders.status")}</th><th>{t("orders.taskProduct")}</th><th>{t("orders.observedPrice")}</th><th>{t("orders.targetPrice")}</th><th>{t("orders.result")}</th><th>{t("orders.timestamp")}</th></tr></thead><tbody>{query.data.map((order) => { const task = tasks.data?.find((item) => item.id === order.task_id); return <tr key={order.id}><td><StatusDot status={order.status} /></td><td><strong>{t("task.productId")} {taskName(order.task_id)}</strong><small>{order.task_id}</small></td><td>{order.observed_price ?? "—"}</td><td>{task ? `$${task.target_price.toFixed(2)}` : "—"}</td><td className={order.error ? "text-danger" : "text-success"}>{order.error ?? t("orders.submitted")}</td><td>{new Date(order.created_at).toLocaleString()}</td></tr>; })}</tbody></table></div> : <div className="empty-state"><span className="empty-mark">↗</span><strong>{t("orders.emptyTitle")}</strong><p>{t("orders.emptyBody")}</p></div>}</section></div>;
}
