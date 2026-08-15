import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthGate } from "./components/AuthGate";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Logs } from "./pages/Logs";
import { Orders } from "./pages/Orders";
import { Settings } from "./pages/Settings";
import { Tasks } from "./pages/Tasks";
import { Updates } from "./pages/Updates";
import "./styles.css";
import { I18nProvider } from "./i18n";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5_000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><I18nProvider><BrowserRouter><AuthGate><Layout><Routes><Route path="/" element={<Dashboard />} /><Route path="/tasks" element={<Tasks />} /><Route path="/orders" element={<Orders />} /><Route path="/logs" element={<Logs />} /><Route path="/updates" element={<Updates />} /><Route path="/settings" element={<Settings />} /><Route path="*" element={<Dashboard />} /></Routes></Layout></AuthGate></BrowserRouter></I18nProvider></QueryClientProvider></React.StrictMode>);
