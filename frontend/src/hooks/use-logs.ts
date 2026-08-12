import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getApiKey } from "../lib/api";

export function useLogs(taskId?: string, level?: string, visible = true) {
  return useQuery({
    queryKey: ["logs", taskId, level],
    queryFn: () => api.logs.list(taskId, level),
    enabled: Boolean(getApiKey()),
    refetchInterval: visible ? 5_000 : false,
  });
}

export function useClearLogs() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.logs.clear,
    onSuccess: () => client.invalidateQueries({ queryKey: ["logs"] }),
  });
}
