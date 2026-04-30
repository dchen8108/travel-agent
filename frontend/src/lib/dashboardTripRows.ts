import type {
  BookingPanelPayload,
  DashboardPayload,
  TrackerPanelPayload,
  TripRow as TripRowValue,
} from "../types";

const UNGROUPED_TRIPS_FILTER_VALUE = "__ungrouped__";

export interface DashboardTripFilters {
  selectedTripGroupIds: string[];
  includeBooked: boolean;
  includeSkipped: boolean;
}

export function buildTripRowLookup(dashboard: DashboardPayload | undefined) {
  const lookup = new Map<string, TripRowValue>();
  if (!dashboard) {
    return lookup;
  }
  for (const row of dashboard.trips) {
    lookup.set(row.trip.tripInstanceId, row);
  }
  for (const item of dashboard.actionItems) {
    if (item.kind === "tripAttention") {
      lookup.set(item.row.trip.tripInstanceId, item.row);
    }
  }
  return lookup;
}

export function filterTripRows(
  dashboard: DashboardPayload | undefined,
  {
    selectedTripGroupIds,
    includeBooked,
    includeSkipped,
  }: DashboardTripFilters,
) {
  if (!dashboard) {
    return [];
  }
  const selectedIds = new Set(selectedTripGroupIds);
  const includeUngrouped = selectedIds.has(UNGROUPED_TRIPS_FILTER_VALUE);
  const groupedSelections = new Set(
    [...selectedIds].filter((value) => value !== UNGROUPED_TRIPS_FILTER_VALUE),
  );

  return dashboard.trips.filter((row) => {
    if (!includeSkipped && row.trip.skipped) {
      return false;
    }
    if (!includeBooked && row.bookedOffer) {
      return false;
    }
    if (!selectedIds.size) {
      return true;
    }
    if (row.trip.tripGroupIds.length === 0) {
      return includeUngrouped;
    }
    return row.trip.tripGroupIds.some((groupId) => groupedSelections.has(groupId));
  });
}

export function bookingPanelPreview(row: TripRowValue | undefined): BookingPanelPayload | null {
  if (!row) {
    return null;
  }
  return {
    trip: row.trip,
    rows: row.bookedOffer ? [{ bookingId: "", offer: row.bookedOffer, warning: "" }] : [],
  };
}

export function trackerPanelPreview(row: TripRowValue | undefined): TrackerPanelPayload | null {
  if (!row || !row.actions.showTrackers) {
    return null;
  }
  const previewRows = row.currentOffer && !row.currentOffer.priceIsStatus
    ? [{
        rowId: "",
        travelDate: row.trip.anchorDate,
        offer: row.currentOffer,
      }]
    : [];
  return {
    trip: row.trip,
    rows: previewRows,
    lastRefreshLabel: "",
    tripAnchorDate: row.trip.anchorDate,
    emptyLabel: row.currentOffer?.statusKind === "unavailable" ? "No live fares right now." : "Checking live fares…",
  };
}
