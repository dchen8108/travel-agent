export function dashboardQueryPrefix() {
  return ["dashboard"] as const;
}

export function dashboardQueryKey(query: string) {
  return [...dashboardQueryPrefix(), query] as const;
}

export function bookingPanelQueryKey(tripInstanceId: string) {
  return ["booking-panel", tripInstanceId] as const;
}

export function bookingFormQueryKey(tripInstanceId: string, bookingId = "") {
  return ["booking-form", tripInstanceId, bookingId || "__create__"] as const;
}

export function trackerPanelQueryKey(tripInstanceId: string) {
  return ["tracker-panel", tripInstanceId] as const;
}

export function unmatchedBookingFormQueryKey(unmatchedBookingId: string) {
  return ["unmatched-booking-form", unmatchedBookingId] as const;
}

export function tripEditorQueryKey(mode: "create" | "edit", tripId: string, query: string) {
  return ["trip-editor", mode, tripId, query] as const;
}
