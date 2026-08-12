import { ReactNode, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, useNavigate } from "react-router-dom";
import { clearApiKey } from "../lib/api";

const navigation = [
  { to: "/", label: "Overview", icon: "◌" },
  { to: "/tasks", label: "Tasks", icon: "▦" },
  { to: "/orders", label: "Orders", icon: "↗" },
  { to: "/logs", label: "Logs", icon: "≡" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export function Layout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const railRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 680px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) return;
    const hidden = isMobile && !mobileOpen;
    if (hidden) rail.setAttribute("inert", "");
    else rail.removeAttribute("inert");
    if (isMobile) rail.setAttribute("aria-hidden", String(hidden));
    else rail.removeAttribute("aria-hidden");
  }, [isMobile, mobileOpen]);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && mobileOpen) {
        setMobileOpen(false);
        window.setTimeout(() => menuRef.current?.focus(), 0);
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const closeMobile = () => {
    setMobileOpen(false);
    window.setTimeout(() => menuRef.current?.focus(), 0);
  };

  const signOut = () => {
    clearApiKey();
    queryClient.getQueryCache().clear();
    setMobileOpen(false);
    navigate("/", { replace: true });
    window.dispatchEvent(new Event("nocix:unauthorized"));
  };

  return (
    <div className="app-shell">
      <button className={`mobile-scrim ${mobileOpen ? "is-open" : ""}`} aria-label="Close navigation" onClick={closeMobile} />
      <aside ref={railRef} id="mobile-navigation" className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="sidebar-top"><div className="brand-lockup"><span className="brand-glyph">N</span><span>NOCIX <b>CONSOLE</b></span></div><button className="icon-button mobile-close" aria-label="Close navigation" onClick={closeMobile}>×</button></div>
        <div className="rail-label">Control room</div>
        <nav aria-label="Primary navigation" className="main-nav">
          {navigation.map((item) => <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={() => isMobile && closeMobile()}><span className="nav-icon">{item.icon}</span>{item.label}</NavLink>)}
        </nav>
        <div className="sidebar-footer"><div className="connection-panel"><span className="status-dot status-dot-good" /><div><strong>API connected</strong><small>Session active</small></div></div><button className="signout" onClick={signOut}>Sign out <span>↪</span></button></div>
      </aside>
      <section className="content-shell">
        <header className="topbar"><button ref={menuRef} className="mobile-menu icon-button" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen(true)}>☰</button><div className="topbar-context"><span className="context-kicker">NOCIX / OPERATIONS</span><span className="context-title">Worker control console</span></div><div className="topbar-meta"><span className="live-pill"><span className="status-dot status-dot-good" /> Live</span><span className="topbar-date">Local session</span></div></header>
        <main className="page-content">{children}</main>
      </section>
    </div>
  );
}
