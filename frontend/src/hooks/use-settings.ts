import { useQuery } from "@tanstack/react-query";
import { api, getApiKey } from "../lib/api";

export const SETTINGS_POLL_INTERVAL = 30_000;

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: api.settings.get,
    enabled: Boolean(getApiKey()),
    refetchInterval: SETTINGS_POLL_INTERVAL,
  });
}
