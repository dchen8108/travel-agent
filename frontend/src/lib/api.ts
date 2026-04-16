import type {
  BookingPanelPayload,
  CollectionCard,
  DashboardPayload,
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

export const api = {
  dashboard(params: URLSearchParams): Promise<DashboardPayload> {
    const query = params.toString();
    return request<DashboardPayload>(`/api/dashboard${query ? `?${query}` : ""}`);
  },
  collection(groupId: string): Promise<CollectionCard> {
    return request<CollectionCard>(`/api/collections/${groupId}`);
  },
  createCollection(label: string): Promise<CollectionCard> {
    return request<CollectionCard>("/api/collections", {
      method: "POST",
      body: JSON.stringify({ label }),
    });
  },
  updateCollection(groupId: string, label: string): Promise<CollectionCard> {
    return request<CollectionCard>(`/api/collections/${groupId}`, {
      method: "PATCH",
      body: JSON.stringify({ label }),
    });
  },
  toggleRecurringTrip(tripId: string, active: boolean): Promise<unknown> {
    return request(`/api/trips/${tripId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ active }),
    });
  },
  deleteTripInstance(tripInstanceId: string): Promise<void> {
    return request(`/api/trip-instances/${tripInstanceId}`, {
      method: "DELETE",
    });
  },
  bookingPanel(tripInstanceId: string, mode: "list" | "create" | "edit", bookingId = ""): Promise<BookingPanelPayload> {
    const params = new URLSearchParams();
    params.set("mode", mode);
    if (bookingId) {
      params.set("booking_id", bookingId);
    }
    return request<BookingPanelPayload>(`/api/trip-instances/${tripInstanceId}/bookings?${params}`);
  },
  createBooking(payload: Record<string, string>): Promise<BookingPanelPayload> {
    return request<BookingPanelPayload>("/api/bookings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateBooking(bookingId: string, payload: Record<string, string>): Promise<BookingPanelPayload> {
    return request<BookingPanelPayload>(`/api/bookings/${bookingId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  unlinkBooking(bookingId: string): Promise<void> {
    return request(`/api/bookings/${bookingId}/unlink`, { method: "POST" });
  },
  linkUnmatchedBooking(unmatchedBookingId: string, tripInstanceId: string): Promise<void> {
    return request(`/api/unmatched-bookings/${unmatchedBookingId}/link`, {
      method: "POST",
      body: JSON.stringify({ tripInstanceId }),
    });
  },
  deleteBooking(bookingId: string): Promise<void> {
    return request(`/api/bookings/${bookingId}`, { method: "DELETE" });
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
