import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getApiKey } from "../lib/api";
import type { TaskInput } from "../lib/types";

export const taskQueryKey = ["tasks"];

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

export function useTaskHistory(taskId: string | null) {
  return useQuery({
    queryKey: ["task-history", taskId],
    queryFn: () => api.tasks.history(taskId as string),
    enabled: Boolean(taskId && getApiKey()),
  });
}
