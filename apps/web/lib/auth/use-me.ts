"use client";

import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => unwrap(await api.GET("/api/v1/auth/me")),
    staleTime: 5 * 60_000,
  });
}

export function useProgramId(): string | undefined {
  return useMe().data?.default_program_id ?? undefined;
}
