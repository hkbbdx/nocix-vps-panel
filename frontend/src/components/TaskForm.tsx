import { FormEvent, useState } from "react";
import type { ProxyMode, Task, TaskInput } from "../lib/types";
import { isValidProxyUrl } from "../lib/proxy";
import { useTranslation } from "../i18n";

interface TaskFormProps {
  task?: Task | null;
  onSubmit: (input: TaskInput | Partial<TaskInput>) => void | Promise<void>;
  onCancel: () => void;
  busy?: boolean;
}

export function TaskForm({ task, onSubmit, onCancel, busy = false }: TaskFormProps) {
  const [goodsId, setGoodsId] = useState(task?.goods_id ?? "");
  const [targetPrice, setTargetPrice] = useState(String(task?.target_price ?? ""));
  const [interval, setInterval] = useState(String(task?.wait_interval ?? 5));
  const [operatingSystem, setOperatingSystem] = useState<"debian" | "ubuntu">(task?.operating_system ?? "debian");
  const [email, setEmail] = useState(task?.email ?? "");
  const [password, setPassword] = useState("");
  const [stockUrl, setStockUrl] = useState(task?.stock_url ?? "");
  const [cartUrl, setCartUrl] = useState(task?.cart_url ?? "");
  const [proxyMode, setProxyMode] = useState<ProxyMode>(task?.proxy_mode ?? "inherit");
  const [proxyConfigured] = useState(task?.proxy_configured ?? false);
  const [proxyChanged, setProxyChanged] = useState(false);
  const [proxyUrl, setProxyUrl] = useState("");
  const [error, setError] = useState("");
  const { t } = useTranslation();

  const validNocixUrl = (value: string) => {
    if (!value.trim()) return true;
    try {
      const parsed = new URL(value);
      const hostname = parsed.hostname.toLowerCase().replace(/\.$/, "");
      return (parsed.protocol === "http:" || parsed.protocol === "https:") &&
        (hostname === "nocix.net" || hostname.endsWith(".nocix.net")) &&
        !parsed.username && !parsed.password && !/\s/.test(value);
    } catch {
      return false;
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const price = Number(targetPrice);
    const seconds = Number(interval);
    if (!goodsId || !/^\d+$/.test(goodsId)) return setError(t("task.productDigits"));
    if (!Number.isFinite(price) || price <= 0) return setError(t("task.priceInvalid"));
    if (!Number.isFinite(seconds) || !Number.isInteger(seconds) || seconds < 2) return setError(t("task.intervalInvalid"));
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setError(t("task.emailInvalid"));
    if (!task && !password) return setError(t("task.accountRequired"));
    if (task && !task.password_configured && !password) return setError(t("task.passwordRequired"));
    if (!validNocixUrl(stockUrl)) return setError(t("task.stockUrlInvalid"));
    if (!validNocixUrl(cartUrl)) return setError(t("task.cartUrlInvalid"));
    const proxyModeChanged = !task || proxyMode !== task.proxy_mode;
    if (proxyMode === "custom" && (!task || !proxyConfigured || proxyChanged || proxyModeChanged) && !isValidProxyUrl(proxyUrl)) return setError(t("task.proxyUrlInvalid"));
    const derivedStockUrl = `https://nocix.net/out-of-stock/?id=${goodsId}`;
    const derivedCartUrl = `https://nocix.net/cart/?id=${goodsId}`;
    const shouldSendProxy = proxyModeChanged || proxyChanged;
    const input = {
      goods_id: goodsId,
      target_price: price,
      wait_interval: seconds,
      operating_system: operatingSystem,
      email,
      ...(password ? { password } : {}),
      ...(stockUrl ? { stock_url: stockUrl } : task ? { stock_url: derivedStockUrl } : {}),
      ...(cartUrl ? { cart_url: cartUrl } : task ? { cart_url: derivedCartUrl } : {}),
      new_customer: false as const,
      payment_method: "paypal" as const,
      auto_submit: true as const,
      ...(shouldSendProxy ? { proxy_mode: proxyMode } : {}),
      ...(shouldSendProxy && proxyMode === "custom" ? { proxy_url: proxyUrl } : {}),
    };
    await onSubmit(input);
  };

  return (
    <form className="task-form" onSubmit={submit} noValidate>
      <div className="dialog-heading">
        <div>
          <p className="eyebrow">{task ? t("task.editEyebrow") : t("task.newEyebrow")}</p>
          <h2 id="task-dialog-title">{task ? t("task.editTitle") : t("task.newTitle")}</h2>
        </div>
        <button className="icon-button" type="button" onClick={onCancel} aria-label={t("task.closeForm")}>×</button>
      </div>
      <div className="form-grid">
        <label>{t("task.productId")}<input inputMode="numeric" value={goodsId} onChange={(event) => setGoodsId(event.target.value)} required /></label>
        <label>{t("task.targetPrice")}<input type="number" min="0.01" step="0.01" value={targetPrice} onChange={(event) => setTargetPrice(event.target.value)} required /></label>
        <label>{t("task.interval")}<input type="number" min="2" step="1" value={interval} onChange={(event) => setInterval(event.target.value)} required /></label>
         <label>{t("task.operatingSystem")}<select value={operatingSystem} onChange={(event) => setOperatingSystem(event.target.value as "debian" | "ubuntu")}><option value="debian">{t("task.osDebian")}</option><option value="ubuntu">{t("task.osUbuntu")}</option></select></label>
        <label>{t("task.email")}<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>{t("task.password")}<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required={!task || !task.password_configured} placeholder={task?.password_configured ? t("task.leaveUnchanged") : undefined} /></label>
        <label className="wide">{t("task.stockUrl")} <span className="muted">{t("task.optional")}</span><input type="url" value={stockUrl} onChange={(event) => setStockUrl(event.target.value)} placeholder={t("task.derivedStock")} /></label>
         <label className="wide">{t("task.cartUrl")} <span className="muted">{t("task.optional")}</span><input type="url" value={cartUrl} onChange={(event) => setCartUrl(event.target.value)} placeholder={t("task.derivedCart")} /></label>
          <label>{t("task.proxyMode")}<select value={proxyMode} onChange={(event) => { const nextMode = event.target.value as ProxyMode; setProxyMode(nextMode); setError(""); if (nextMode !== "custom") { setProxyUrl(""); setProxyChanged(false); } }}><option value="inherit">{t("task.proxyInherit")}</option><option value="custom">{t("task.proxyCustom")}</option><option value="direct">{t("task.proxyDirect")}</option></select></label>
          {proxyMode === "custom" && <label>{t("task.customProxyUrl")}<input type="password" autoComplete="off" value={proxyUrl} onChange={(event) => { setProxyUrl(event.target.value); setProxyChanged(true); }} placeholder={t("task.proxyFormat")} /></label>}
      </div>
      <div className="payment-lock" role="note">
        <span className="payment-mark">P</span>
        <div><strong>{t("task.paymentMethod")}<span>PayPal</span></strong><span>{t("task.paypalCopy")}</span></div>
      </div>
      <label className="confirm-row"><input type="checkbox" checked readOnly /> <span><strong>{t("task.autoSubmit")}</strong><small>{t("task.autoSubmitCopy")}</small></span></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="button-secondary" onClick={onCancel}>{t("task.cancel")}</button><button type="submit" className="button-primary" disabled={busy}>{busy ? t("task.saving") : task ? t("task.saveChanges") : t("task.create")}</button></div>
    </form>
  );
}
