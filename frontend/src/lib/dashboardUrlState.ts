export const DASHBOARD_PARAM_KEYS = {
  bookingId: "booking_id",
  bookingMode: "booking_mode",
  createCollection: "create_group",
  editCollectionId: "edit_group_id",
  includeBooked: "include_booked",
  message: "message",
  messageKind: "message_kind",
  panel: "panel",
  tripGroupId: "trip_group_id",
  tripInstanceId: "trip_instance_id",
} as const;

export type CollectionEditorState =
  | { mode: "create" }
  | { mode: "edit"; groupId: string }
  | null;

export type BookingPanelMode = "list" | "create" | "edit";

export interface BookingPanelState {
  mode: BookingPanelMode;
  bookingId: string;
}

export interface DashboardUrlState {
  panel: string | null;
  panelTripInstanceId: string;
  collectionEditor: CollectionEditorState;
  bookingPanelState: BookingPanelState;
  selectedTripGroupIds: string[];
  includeBooked: boolean;
}

export function parseCollectionEditorState(searchParams: URLSearchParams): CollectionEditorState {
  if (searchParams.get(DASHBOARD_PARAM_KEYS.createCollection) === "1") {
    return { mode: "create" };
  }
  const groupId = searchParams.get(DASHBOARD_PARAM_KEYS.editCollectionId) ?? "";
  return groupId ? { mode: "edit", groupId } : null;
}

export function parseBookingPanelState(searchParams: URLSearchParams): BookingPanelState {
  return {
    mode: (searchParams.get(DASHBOARD_PARAM_KEYS.bookingMode) as BookingPanelMode | null) ?? "list",
    bookingId: searchParams.get(DASHBOARD_PARAM_KEYS.bookingId) ?? "",
  };
}

export function parseDashboardUrlState(searchParams: URLSearchParams): DashboardUrlState {
  return {
    panel: searchParams.get(DASHBOARD_PARAM_KEYS.panel),
    panelTripInstanceId: searchParams.get(DASHBOARD_PARAM_KEYS.tripInstanceId) ?? "",
    collectionEditor: parseCollectionEditorState(searchParams),
    bookingPanelState: parseBookingPanelState(searchParams),
    selectedTripGroupIds: searchParams.getAll(DASHBOARD_PARAM_KEYS.tripGroupId),
    includeBooked: searchParams.get(DASHBOARD_PARAM_KEYS.includeBooked) !== "false",
  };
}

export function buildDashboardFilters(
  selectedTripGroupIds: string[],
  includeBooked: boolean,
): URLSearchParams {
  const params = new URLSearchParams();
  for (const value of [...selectedTripGroupIds].sort()) {
    params.append(DASHBOARD_PARAM_KEYS.tripGroupId, value);
  }
  if (!includeBooked) {
    params.set(DASHBOARD_PARAM_KEYS.includeBooked, "false");
  }
  return params;
}
