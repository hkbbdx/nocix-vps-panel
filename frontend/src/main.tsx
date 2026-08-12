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
import "./styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5_000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><AuthGate><Layout><Routes><Route path="/" element={<Dashboard />} /><Route path="/tasks" element={<Tasks />} /><Route path="/orders" element={<Orders />} /><Route path="/logs" element={<Logs />} /><Route path="/settings" element={<Settings />} /><Route path="*" element={<Dashboard />} /></Routes></Layout></AuthGate></BrowserRouter></QueryClientProvider></React.StrictMode>);
