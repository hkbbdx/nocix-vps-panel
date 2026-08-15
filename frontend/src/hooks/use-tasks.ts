import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, getApiKey } from "../lib/api";
import type { TaskInput, TaskStatus } from "../lib/types";

export const taskQueryKey = ["tasks"];
export const LOGIN_STATE_POLL_INTERVAL = 5_000;
const loginStateQueryKey = ["task-login-state"];

function invalidateLoginData(client: ReturnType<typeof useQueryClient>) {
  void client.invalidateQueries({ queryKey: taskQueryKey });
  void client.invalidateQueries({ queryKey: ["stats"] });
  void client.invalidateQueries({ queryKey: ["logs"] });
  void client.invalidateQueries({ queryKey: ["orders"] });
  void client.invalidateQueries({ queryKey: loginStateQueryKey });
}

export function useTasks() {
  return useQuery({
    queryKey: taskQueryKey,
    queryFn: api.tasks.list,
    enabled: Boolean(getApiKey()),
  });
}

export function useTaskMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: taskQueryKey });
  const create = useMutation({ mutationFn: (input: TaskInput) => api.tasks.create(input), onSuccess: refresh });
  const update = useMutation({ mutationFn: ({ id, input }: { id: string; input: Partial<TaskInput> }) => api.tasks.update(id, input), onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.tasks.remove, onSuccess: refresh });
  const action = useMutation({ mutationFn: ({ id, action }: { id: string; action: "start" | "pause" | "resume" | "stop" | "check" }) => api.tasks.action(id, action), onSuccess: refresh });
  return { create, update, remove, action };
}

export function useLoginState(taskId: string | null, status: TaskStatus) {
  const waiting = status === "waiting_for_email_code";
  const client = useQueryClient();
  const handledTerminalRef = useRef<string | null>(null);
  const [terminal, setTerminal] = useState(false);
  useEffect(() => {
    if (!waiting) {
      setTerminal(false);
      handledTerminalRef.current = null;
    }
  }, [waiting]);
  const query = useQuery({
    queryKey: [...loginStateQueryKey, taskId],
    queryFn: () => api.tasks.loginState(taskId as string),
    enabled: Boolean(taskId && getApiKey() && waiting && !terminal),
    refetchInterval: (current) => {
      const liveState = current.state.data;
      const terminalError = current.state.error instanceof ApiError && current.state.error.status === 409;
      if (!waiting || terminalError || (liveState && (!liveState.waiting || liveState.status !== "waiting_for_email_code"))) return false;
      return LOGIN_STATE_POLL_INTERVAL;
    },
  });

  useEffect(() => {
    const liveState = query.data;
    const terminalError = query.error instanceof ApiError && query.error.status === 409;
    if (!waiting || (!terminalError && (!liveState || liveState.waiting && liveState.status === "waiting_for_email_code"))) return;
    const terminalKey = `${taskId}:${liveState?.status ?? "409"}:${liveState?.last_error ?? ""}`;
    if (handledTerminalRef.current === terminalKey) return;
    handledTerminalRef.current = terminalKey;
    setTerminal(true);
    invalidateLoginData(client);
  }, [client, query.data, query.error, taskId, waiting]);

  return query;
}

export function useLoginMutations() {
  const client = useQueryClient();
  const codeRef = useRef<string | null>(null);
  const refreshLoginData = () => invalidateLoginData(client);
  const submitEmailCodeMutation = useMutation({
    // Keep the one-time code out of mutation variables and the query cache.
    mutationFn: ({ id }: { id: string }) => api.tasks.submitEmailCode(id, codeRef.current ?? ""),
    onSuccess: refreshLoginData,
  });
  const cancelLogin = useMutation({
    mutationFn: api.tasks.cancelLogin,
    onSuccess: refreshLoginData,
  });
  return {
    submitEmailCode: {
      ...submitEmailCodeMutation,
      mutateAsync: async ({ id, code }: { id: string; code: string }) => {
        codeRef.current = code;
        try {
          return await submitEmailCodeMutation.mutateAsync({ id });
        } finally {
          codeRef.current = null;
        }
      },
    },
    cancelLogin,
  };
}

export function useTaskHistory(taskId: string | null) {
  return useQuery({
    queryKey: ["task-history", taskId],
    queryFn: () => api.tasks.history(taskId as string),
    enabled: Boolean(taskId && getApiKey()),
  });
}
