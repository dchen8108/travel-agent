import type { QueryClient } from "@tanstack/react-query";

import { api } from "./api";

export function prefetchTripEditorFromHref(queryClient: QueryClient, href: string): Promise<void | unknown> {
  const url = new URL(href, window.location.origin);
  const params = new URLSearchParams(url.search);

  if (url.pathname === "/trips/new" || url.pathname === "/app/trips/new") {
    return queryClient.prefetchQuery({
      queryKey: ["trip-editor", "create", "", params.toString()],
      queryFn: () => api.tripEditorNew(params),
    });
  }

  const match = url.pathname.match(/^\/(?:app\/)?trips\/([^/]+)\/edit$/);
  if (!match) {
    return Promise.resolve();
  }
  const tripId = match[1];
  return queryClient.prefetchQuery({
    queryKey: ["trip-editor", "edit", tripId, params.toString()],
    queryFn: () => api.tripEditorEdit(tripId, params),
  });
}
