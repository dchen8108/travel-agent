import type { QueryClient, QueryKey } from "@tanstack/react-query";

export function prefetchOnce<TData>(
  queryClient: QueryClient,
  {
    queryKey,
    queryFn,
  }: {
    queryKey: QueryKey;
    queryFn: () => Promise<TData>;
  },
) {
  const state = queryClient.getQueryState<TData>(queryKey);
  if (state?.fetchStatus === "fetching" || state?.status === "success") {
    return Promise.resolve(state.data);
  }
  return queryClient.prefetchQuery({ queryKey, queryFn });
}
