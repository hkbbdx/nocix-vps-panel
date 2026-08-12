import { FormEvent, useState } from "react";
import type { Task, TaskInput } from "../lib/types";

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
  const [error, setError] = useState("");

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
    if (!goodsId || !/^\d+$/.test(goodsId)) return setError("Product ID must contain digits only.");
    if (!Number.isFinite(price) || price <= 0) return setError("Target price must be a finite number greater than zero.");
    if (!Number.isFinite(seconds) || !Number.isInteger(seconds) || seconds < 2) return setError("Check interval must be a finite whole number of at least 2 seconds.");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setError("Enter a valid email address.");
    if (!task && !password) return setError("Existing NOCIX email and password are required.");
    if (task && !task.password_configured && !password) return setError("Existing NOCIX password is required for this task.");
    if (!validNocixUrl(stockUrl)) return setError("Stock URL must be valid HTTP(S) syntax on a NOCIX host.");
    if (!validNocixUrl(cartUrl)) return setError("Cart URL must be valid HTTP(S) syntax on a NOCIX host.");
    const derivedStockUrl = `https://nocix.net/out-of-stock/?id=${goodsId}`;
    const derivedCartUrl = `https://nocix.net/cart/?id=${goodsId}`;
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
    };
    await onSubmit(input);
  };

  return (
    <form className="task-form" onSubmit={submit} noValidate>
      <div className="dialog-heading">
        <div>
          <p className="eyebrow">{task ? "Edit monitor" : "New monitor"}</p>
          <h2 id="task-dialog-title">{task ? "Tune a task" : "Watch a NOCIX product"}</h2>
        </div>
        <button className="icon-button" type="button" onClick={onCancel} aria-label="Close task form">×</button>
      </div>
      <div className="form-grid">
        <label>Product ID<input inputMode="numeric" value={goodsId} onChange={(event) => setGoodsId(event.target.value)} required /></label>
        <label>Target price<input type="number" min="0.01" step="0.01" value={targetPrice} onChange={(event) => setTargetPrice(event.target.value)} required /></label>
        <label>Check interval (seconds)<input type="number" min="2" step="1" value={interval} onChange={(event) => setInterval(event.target.value)} required /></label>
        <label>Operating system<select value={operatingSystem} onChange={(event) => setOperatingSystem(event.target.value as "debian" | "ubuntu")}><option value="debian">Debian</option><option value="ubuntu">Ubuntu</option></select></label>
        <label>Existing NOCIX email<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>NOCIX password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required={!task || !task.password_configured} placeholder={task?.password_configured ? "Leave unchanged" : undefined} /></label>
        <label className="wide">Stock URL <span className="muted">optional</span><input type="url" value={stockUrl} onChange={(event) => setStockUrl(event.target.value)} placeholder="Derived from product ID when blank" /></label>
        <label className="wide">Cart URL <span className="muted">optional</span><input type="url" value={cartUrl} onChange={(event) => setCartUrl(event.target.value)} placeholder="Derived from product ID when blank" /></label>
      </div>
      <div className="payment-lock" role="note">
        <span className="payment-mark">P</span>
        <div><strong>Payment method: <span>PayPal</span></strong><span>Checkout uses PayPal already saved in NOCIX.</span></div>
      </div>
      <label className="confirm-row"><input type="checkbox" checked readOnly /> <span><strong>Automatic submission enabled</strong><small>Confirmed: submit once the target product and price match.</small></span></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" className="button-secondary" onClick={onCancel}>Cancel</button><button type="submit" className="button-primary" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Create task"}</button></div>
    </form>
  );
}
