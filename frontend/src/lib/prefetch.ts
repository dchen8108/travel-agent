import type { QueryClient, QueryKey } from "@tanstack/react-query";

export function prefetchOnce<TData>(
  queryClient: QueryClient,
  {
    queryKey,
    queryFn,
    staleTime = 30_000,
  }: {
    queryKey: QueryKey;
    queryFn: () => Promise<TData>;
    staleTime?: number;
  },
) {
  const state = queryClient.getQueryState<TData>(queryKey);
  const isFresh = !!state?.dataUpdatedAt && Date.now() - state.dataUpdatedAt < staleTime;
  if (state?.fetchStatus === "fetching" || (state?.status === "success" && isFresh)) {
    return Promise.resolve(state.data);
  }
  return queryClient.prefetchQuery({ queryKey, queryFn });
}
