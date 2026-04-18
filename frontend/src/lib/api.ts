import type {
  BookingFormPayload,
  BookingMutationPayload,
  BookingPanelPayload,
  DashboardMutationPayload,
  DashboardPayload,
  MutationAckPayload,
  UnmatchedBookingFormPayload,
  TripEditorPayload,
  TripEditorRouteOption,
  TripEditorValues,
  TrackerPanelPayload,
} from "../types";

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = String(payload.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function withDashboardFilters(path: string, filters?: URLSearchParams): string {
  const query = filters?.toString() ?? "";
  return query ? `${path}?${query}` : path;
}

export const api = {
  dashboard(params: URLSearchParams): Promise<DashboardPayload> {
    const query = params.toString();
    return request<DashboardPayload>(`/api/dashboard${query ? `?${query}` : ""}`);
  },
  createCollection(label: string, filters?: URLSearchParams): Promise<DashboardMutationPayload> {
    return request<DashboardMutationPayload>(withDashboardFilters("/api/collections", filters), {
      method: "POST",
      body: JSON.stringify({ label }),
    });
  },
  updateCollection(groupId: string, label: string, filters?: URLSearchParams): Promise<DashboardMutationPayload> {
    return request<DashboardMutationPayload>(withDashboardFilters(`/api/collections/${groupId}`, filters), {
      method: "PATCH",
      body: JSON.stringify({ label }),
    });
  },
  deleteCollection(groupId: string): Promise<void> {
    return request<void>(`/api/collections/${groupId}`, {
      method: "DELETE",
    });
  },
  toggleRecurringTrip(tripId: string, active: boolean, filters?: URLSearchParams): Promise<{ tripId: string; active: boolean }> {
    return request<{ tripId: string; active: boolean }>(withDashboardFilters(`/api/trips/${tripId}/status`, filters), {
      method: "PATCH",
      body: JSON.stringify({ active }),
    });
  },
  deleteTripInstance(tripInstanceId: string, filters?: URLSearchParams): Promise<DashboardMutationPayload> {
    return request<DashboardMutationPayload>(withDashboardFilters(`/api/trip-instances/${tripInstanceId}`, filters), {
      method: "DELETE",
    });
  },
  bookingPanel(tripInstanceId: string): Promise<BookingPanelPayload> {
    return request<BookingPanelPayload>(`/api/trip-instances/${tripInstanceId}/bookings?mode=list`);
  },
  bookingForm(tripInstanceId: string, bookingId = ""): Promise<BookingFormPayload> {
    const params = new URLSearchParams();
    if (bookingId) {
      params.set("booking_id", bookingId);
    }
    const query = params.toString();
    return request<BookingFormPayload>(`/api/trip-instances/${tripInstanceId}/booking-form${query ? `?${query}` : ""}`);
  },
  unmatchedBookingForm(unmatchedBookingId: string): Promise<UnmatchedBookingFormPayload> {
    return request<UnmatchedBookingFormPayload>(`/api/unmatched-bookings/${unmatchedBookingId}/form`);
  },
  createBooking(payload: Record<string, string>, filters?: URLSearchParams): Promise<BookingMutationPayload> {
    return request<BookingMutationPayload>(withDashboardFilters("/api/bookings", filters), {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateBooking(bookingId: string, payload: Record<string, string>, filters?: URLSearchParams): Promise<BookingMutationPayload> {
    return request<BookingMutationPayload>(withDashboardFilters(`/api/bookings/${bookingId}`, filters), {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  unlinkBooking(bookingId: string, filters?: URLSearchParams): Promise<BookingMutationPayload> {
    return request<BookingMutationPayload>(withDashboardFilters(`/api/bookings/${bookingId}/unlink`, filters), { method: "POST" });
  },
  linkUnmatchedBooking(unmatchedBookingId: string, tripInstanceId: string, filters?: URLSearchParams): Promise<MutationAckPayload> {
    return request<MutationAckPayload>(withDashboardFilters(`/api/unmatched-bookings/${unmatchedBookingId}/link`, filters), {
      method: "POST",
      body: JSON.stringify({ tripInstanceId }),
    });
  },
  updateUnmatchedBooking(unmatchedBookingId: string, payload: Record<string, string>, filters?: URLSearchParams): Promise<MutationAckPayload> {
    return request<MutationAckPayload>(withDashboardFilters(`/api/unmatched-bookings/${unmatchedBookingId}`, filters), {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  deleteBooking(bookingId: string, filters?: URLSearchParams): Promise<BookingMutationPayload> {
    return request<BookingMutationPayload>(withDashboardFilters(`/api/bookings/${bookingId}`, filters), { method: "DELETE" });
  },
  trackerPanel(tripInstanceId: string): Promise<TrackerPanelPayload> {
    return request<TrackerPanelPayload>(`/api/trip-instances/${tripInstanceId}/trackers`);
  },
  tripEditorNew(params: URLSearchParams): Promise<TripEditorPayload> {
    const query = params.toString();
    return request<TripEditorPayload>(`/api/trips/new-form${query ? `?${query}` : ""}`);
  },
  tripEditorEdit(tripId: string, params: URLSearchParams): Promise<TripEditorPayload> {
    const query = params.toString();
    return request<TripEditorPayload>(`/api/trips/${tripId}/edit-form${query ? `?${query}` : ""}`);
  },
  createTrip(values: TripEditorValues, routeOptions: TripEditorRouteOption[], sourceUnmatchedBookingId: string): Promise<{ message: string; redirectTo: string }> {
    return request<{ message: string; redirectTo: string }>("/api/trips/editor", {
      method: "POST",
      body: JSON.stringify({
        ...values,
        routeOptions,
        sourceUnmatchedBookingId,
      }),
    });
  },
  updateTrip(tripId: string, values: TripEditorValues, routeOptions: TripEditorRouteOption[], sourceUnmatchedBookingId: string): Promise<{ message: string; redirectTo: string }> {
    return request<{ message: string; redirectTo: string }>(`/api/trips/${tripId}/editor`, {
      method: "PATCH",
      body: JSON.stringify({
        ...values,
        routeOptions,
        sourceUnmatchedBookingId,
      }),
    });
  },
  detachTripInstance(tripInstanceId: string): Promise<{ message: string; redirectTo: string }> {
    return request<{ message: string; redirectTo: string }>(`/api/trip-instances/${tripInstanceId}/detach`, {
      method: "POST",
    });
  },
};
