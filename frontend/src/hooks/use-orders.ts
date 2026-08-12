import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getApiKey } from "../lib/api";

export const ORDERS_POLL_INTERVAL = 15_000;

export function useOrders() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: api.orders.list,
    enabled: Boolean(getApiKey()),
    refetchInterval: ORDERS_POLL_INTERVAL,
  });
}

export function useClearOrders() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.orders.clear,
    onSuccess: () => client.invalidateQueries({ queryKey: ["orders"] }),
  });
}
