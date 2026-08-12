import { useQuery } from "@tanstack/react-query";
import { api, getApiKey } from "../lib/api";

export function useDashboard() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    enabled: Boolean(getApiKey()),
    refetchInterval: 15_000,
  });
}
