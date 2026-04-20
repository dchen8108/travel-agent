import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ActionItemsSection } from "../components/ActionItemsSection";
import { BookingFormModal } from "../components/BookingFormModal";
import { BookingInspector } from "../components/BookingInspector";
import { BookingPanel } from "../components/BookingPanel";
import { CollectionCard } from "../components/CollectionCard";
import { CollectionNameEditor } from "../components/CollectionNameEditor";
import { useConfirm } from "../components/ConfirmProvider";
import { FilterBar } from "../components/FilterBar";
import { InspectorShell } from "../components/InspectorShell";
import { PrefetchLink } from "../components/PrefetchLink";
import { TrackerInspector } from "../components/TrackerInspector";
import { TrackerPanel } from "../components/TrackerPanel";
import { TripRow } from "../components/TripRow";
import { UnmatchedBookingEditorModal } from "../components/UnmatchedBookingEditorModal";
import { useToast } from "../components/ToastProvider";
import { api } from "../lib/api";
import { prefetchOnce } from "../lib/prefetch";
import {
  bookingFormQueryKey,
  bookingPanelQueryKey,
  dashboardQueryKey,
  dashboardQueryPrefix,
  trackerPanelQueryKey,
} from "../lib/queryKeys";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import type {
  BookingPanelPayload,
  CollectionCard as CollectionCardValue,
  DashboardPayload,
  TrackerPanelPayload,
  TripRow as TripRowValue,
} from "../types";

function initialCollectionEditor(searchParams: URLSearchParams) {
  if (searchParams.get("create_group") === "1") {
    return { mode: "create" as const };
  }
  const groupId = searchParams.get("edit_group_id") ?? "";
  return groupId ? { mode: "edit" as const, groupId } : null;
}

function initialBookingPanelState(searchParams: URLSearchParams) {
  return {
    mode: (searchParams.get("booking_mode") as "list" | "create" | "edit" | null) ?? "list",
    bookingId: searchParams.get("booking_id") ?? "",
  };
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function optimisticSetRecurringTripActive(dashboard: DashboardPayload, tripId: string, active: boolean): DashboardPayload {
  return {
    ...dashboard,
    collections: dashboard.collections.map((collection) => ({
      ...collection,
      recurringTrips: collection.recurringTrips.map((trip) => (
        trip.tripId === tripId ? { ...trip, active } : trip
      )),
    })),
  };
}

function optimisticRemoveTripInstance(dashboard: DashboardPayload, tripInstanceId: string): DashboardPayload {
  const removedRow = dashboard.trips.find((row) => row.trip.tripInstanceId === tripInstanceId);

  return {
    ...dashboard,
    counts: {
      totalUpcoming: Math.max(0, dashboard.counts.totalUpcoming - (removedRow ? 1 : 0)),
      totalBooked: Math.max(0, dashboard.counts.totalBooked - (removedRow?.bookedOffer ? 1 : 0)),
    },
    collections: dashboard.collections.map((collection) => ({
      ...collection,
      upcomingTrips: collection.upcomingTrips.filter((trip) => trip.tripInstanceId !== tripInstanceId),
    })),
    trips: dashboard.trips.filter((row) => row.trip.tripInstanceId !== tripInstanceId),
    actionItems: dashboard.actionItems.filter((item) => (
      item.kind === "unmatchedBooking" || item.row.trip.tripInstanceId !== tripInstanceId
    )),
  };
}

function optimisticRemoveUnmatchedBooking(dashboard: DashboardPayload, unmatchedBookingId: string): DashboardPayload {
  return {
    ...dashboard,
    actionItems: dashboard.actionItems.filter((item) => (
      item.kind !== "unmatchedBooking" || item.unmatchedBookingId !== unmatchedBookingId
    )),
  };
}

function optimisticRemoveCollection(dashboard: DashboardPayload, groupId: string): DashboardPayload {
  return {
    ...dashboard,
    filters: {
      ...dashboard.filters,
      selectedTripGroupIds: dashboard.filters.selectedTripGroupIds.filter((value) => value !== groupId),
      groupOptions: dashboard.filters.groupOptions.filter((option) => option.value !== groupId),
    },
    collections: dashboard.collections.filter((collection) => collection.groupId !== groupId),
  };
}

function tripRowLookup(dashboard: DashboardPayload | undefined) {
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

function bookingPanelPreview(row: TripRowValue | undefined): BookingPanelPayload | null {
  if (!row) {
    return null;
  }
  return {
    trip: row.trip,
    rows: row.bookedOffer ? [{ bookingId: "", offer: row.bookedOffer, warning: "" }] : [],
  };
}

function trackerPanelPreview(row: TripRowValue | undefined): TrackerPanelPayload | null {
  if (!row) {
    return null;
  }
  return {
    trip: row.trip,
    rows: row.currentOffer
      ? [
          {
            rowId: "",
            travelDate: row.trip.anchorDate,
            offer: row.currentOffer,
          },
        ]
      : [],
    lastRefreshLabel: "",
    tripAnchorDate: row.trip.anchorDate,
  };
}

export function DashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { confirm } = useConfirm();
  const [collectionEditor, setCollectionEditor] = useState<{ mode: "create" | "edit"; groupId?: string } | null>(() => (
    initialCollectionEditor(searchParams)
  ));
  const [bookingPanelState, setBookingPanelState] = useState<{ mode: "list" | "create" | "edit"; bookingId: string }>(() => (
    initialBookingPanelState(searchParams)
  ));
  const [editingUnmatchedBookingId, setEditingUnmatchedBookingId] = useState("");
  const [useDesktopInspector, setUseDesktopInspector] = useState(false);

  const panel = searchParams.get("panel");
  const panelTripInstanceId = searchParams.get("trip_instance_id") ?? "";
  const selectedTripGroupIds = searchParams.getAll("trip_group_id");
  const includeBooked = searchParams.get("include_booked") !== "false";

  const dashboardFilters = useMemo(() => {
    const params = new URLSearchParams();
    for (const value of [...selectedTripGroupIds].sort()) {
      params.append("trip_group_id", value);
    }
    if (!includeBooked) {
      params.set("include_booked", "false");
    }
    return params;
  }, [includeBooked, selectedTripGroupIds]);
  const dashboardQueryString = dashboardFilters.toString();

  const dashboardQuery = useQuery({
    queryKey: dashboardQueryKey(dashboardQueryString),
    queryFn: () => api.dashboard(dashboardFilters),
  });
  const visibleTripRows = useMemo(() => tripRowLookup(dashboardQuery.data), [dashboardQuery.data]);

  useEffect(() => {
    const nextEditor = initialCollectionEditor(searchParams);
    if (nextEditor) {
      setCollectionEditor(nextEditor);
    }
  }, [searchParams]);

  useEffect(() => {
    const state = location.state as { toast?: { message: string; kind?: "success" | "error" } } | null;
    const toast = state?.toast;
    if (!toast?.message) {
      return;
    }
    pushToast({ message: toast.message, kind: toast.kind });
    navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: null });
  }, [location.hash, location.pathname, location.search, location.state, navigate, pushToast]);

  useEffect(() => {
    const message = searchParams.get("message");
    if (!message) {
      return;
    }
    pushToast({
      message,
      kind: searchParams.get("message_kind") === "error" ? "error" : "success",
    });
    const next = new URLSearchParams(searchParams);
    next.delete("message");
    next.delete("message_kind");
    setSearchParams(next, { replace: true });
  }, [pushToast, searchParams, setSearchParams]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const inspectorMediaQuery = window.matchMedia("(min-width: 1180px)");
    const update = () => {
      setUseDesktopInspector(inspectorMediaQuery.matches);
    };
    update();
    inspectorMediaQuery.addEventListener("change", update);
    return () => {
      inspectorMediaQuery.removeEventListener("change", update);
    };
  }, []);

  useEffect(() => {
    if (panel === "bookings" && panelTripInstanceId) {
      if (searchParams.has("booking_mode") || searchParams.has("booking_id")) {
        setBookingPanelState(initialBookingPanelState(searchParams));
      }
      return;
    }
    setBookingPanelState({ mode: "list", bookingId: "" });
  }, [panel, panelTripInstanceId, searchParams]);

  useEffect(() => {
    const tripRows = dashboardQuery.data?.trips.slice(0, 4) ?? [];
    if (!tripRows.length) {
      return;
    }

    const prefetchVisibleRows = () => {
      for (const row of tripRows) {
        if (row.actions.showBookingModal || row.actions.canCreateBooking) {
          prefetchBookingPanel(row.trip.tripInstanceId);
        }
        if (row.actions.showTrackers) {
          prefetchTrackerPanel(row.trip.tripInstanceId);
        }
      }
    };

    if ("requestIdleCallback" in window) {
      const idleId = window.requestIdleCallback(prefetchVisibleRows, { timeout: 600 });
      return () => window.cancelIdleCallback(idleId);
    }

    const timeoutId = globalThis.setTimeout(prefetchVisibleRows, 250);
    return () => globalThis.clearTimeout(timeoutId);
  }, [dashboardQuery.data]);

  function replaceCurrentDashboard(next: DashboardPayload) {
    queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), next);
    void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
  }

  function refreshCurrentDashboard() {
    void queryClient.invalidateQueries({ queryKey: dashboardQueryKey(dashboardQueryString) });
  }

  const collectionMutation = useMutation({
    mutationFn: async ({ label, groupId }: { label: string; groupId?: string }) => (
      groupId ? api.updateCollection(groupId, label, dashboardFilters) : api.createCollection(label, dashboardFilters)
    ),
    onSuccess: ({ dashboard }) => {
      setCollectionEditor(null);
      clearCollectionEditorParams();
      replaceCurrentDashboard(dashboard);
      pushToast({ message: "Collection saved" });
    },
  });

  const deleteCollectionMutation = useMutation({
    mutationFn: (groupId: string) => api.deleteCollection(groupId),
    onMutate: async (groupId) => {
      await queryClient.cancelQueries({ queryKey: dashboardQueryKey(dashboardQueryString) });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardQueryKey(dashboardQueryString));
      if (previous) {
        queryClient.setQueryData(
          dashboardQueryKey(dashboardQueryString),
          optimisticRemoveCollection(previous, groupId),
        );
      }
      return { previous };
    },
    onError: (error, _groupId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to delete collection."), kind: "error" });
    },
    onSuccess: (_result, groupId) => {
      if (selectedTripGroupIds.includes(groupId)) {
        const next = new URLSearchParams(searchParams);
        const remaining = next.getAll("trip_group_id").filter((value) => value !== groupId);
        next.delete("trip_group_id");
        remaining.forEach((value) => next.append("trip_group_id", value));
        setSearchParams(next, { replace: true });
      }
      setCollectionEditor((current) => (
        current?.mode === "edit" && current.groupId === groupId ? null : current
      ));
      void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
      pushToast({ message: "Collection deleted" });
    },
  });

  const toggleTripMutation = useMutation({
    mutationFn: ({ tripId, active }: { tripId: string; active: boolean }) => api.toggleRecurringTrip(tripId, active, dashboardFilters),
    onMutate: async ({ tripId, active }) => {
      await queryClient.cancelQueries({ queryKey: dashboardQueryKey(dashboardQueryString) });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardQueryKey(dashboardQueryString));
      if (previous) {
        queryClient.setQueryData(
          dashboardQueryKey(dashboardQueryString),
          optimisticSetRecurringTripActive(previous, tripId, active),
        );
      }
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to update recurring trip."), kind: "error" });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
    },
  });

  const deleteTripMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.deleteTripInstance(tripInstanceId, dashboardFilters),
    onMutate: async (tripInstanceId) => {
      await queryClient.cancelQueries({ queryKey: dashboardQueryKey(dashboardQueryString) });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardQueryKey(dashboardQueryString));
      if (previous) {
        queryClient.setQueryData(
          dashboardQueryKey(dashboardQueryString),
          optimisticRemoveTripInstance(previous, tripInstanceId),
        );
      }
      return { previous };
    },
    onError: (error, _tripInstanceId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to delete trip."), kind: "error" });
    },
    onSuccess: ({ dashboard }, tripInstanceId) => {
      replaceCurrentDashboard(dashboard);
      if (panelTripInstanceId === tripInstanceId) {
        closePanel();
      }
      pushToast({ message: "Trip deleted" });
    },
  });

  const unmatchedMutation = useMutation<
    unknown,
    unknown,
    {
      unmatchedBookingId: string;
      tripInstanceId?: string;
      kind: "link" | "delete";
    },
    { previous?: DashboardPayload }
  >({
    mutationFn: ({
      unmatchedBookingId,
      tripInstanceId,
      kind,
    }) => {
      if (kind === "delete") {
        return api.deleteBooking(unmatchedBookingId, dashboardFilters);
      }
      if (!tripInstanceId) {
        throw new Error("Choose a scheduled trip.");
      }
      return api.linkUnmatchedBooking(unmatchedBookingId, tripInstanceId, dashboardFilters);
    },
    onMutate: async ({ unmatchedBookingId }) => {
      await queryClient.cancelQueries({ queryKey: dashboardQueryKey(dashboardQueryString) });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardQueryKey(dashboardQueryString));
      if (previous) {
        queryClient.setQueryData(
          dashboardQueryKey(dashboardQueryString),
          optimisticRemoveUnmatchedBooking(previous, unmatchedBookingId),
        );
      }
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to update booking."), kind: "error" });
    },
    onSuccess: () => {
      refreshCurrentDashboard();
    },
  });

  function toggleGroupFilter(groupId: string) {
    const next = new URLSearchParams(searchParams);
    const current = new Set(next.getAll("trip_group_id"));
    if (current.has(groupId)) {
      current.delete(groupId);
    } else {
      current.add(groupId);
    }
    next.delete("trip_group_id");
    [...current].forEach((value) => next.append("trip_group_id", value));
    setSearchParams(next, { replace: true });
  }

  function clearCollectionEditorParams() {
    if (!searchParams.has("create_group") && !searchParams.has("edit_group_id")) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("create_group");
    next.delete("edit_group_id");
    setSearchParams(next, { replace: true });
  }

  function startCreateCollection() {
    setCollectionEditor({ mode: "create" });
    clearCollectionEditorParams();
  }

  function stopCollectionEditing() {
    setCollectionEditor(null);
    clearCollectionEditorParams();
  }

  function startEditCollection(groupId: string) {
    setCollectionEditor({ mode: "edit", groupId });
    clearCollectionEditorParams();
  }

  async function handleDeleteCollection(groupId: string, label: string) {
    const approved = await confirm({
      title: `Delete ${label}?`,
      description: "Trips will remain, but this collection will be removed from them.",
      actionLabel: "Delete collection",
      cancelLabel: "Keep collection",
      tone: "danger",
    });
    if (!approved) {
      return;
    }
    try {
      await deleteCollectionMutation.mutateAsync(groupId);
    } catch {
      // rollback + error toast handled in mutation lifecycle
    }
  }

  function toggleBookedFilter() {
    const next = new URLSearchParams(searchParams);
    if (includeBooked) {
      next.set("include_booked", "false");
    } else {
      next.delete("include_booked");
    }
    setSearchParams(next, { replace: true });
  }

  function prefetchBookingPanel(tripInstanceId: string) {
    void prefetchOnce(queryClient, {
      queryKey: bookingPanelQueryKey(tripInstanceId),
      queryFn: () => api.bookingPanel(tripInstanceId),
    });
  }

  function prefetchBookingForm(tripInstanceId: string, bookingId = "") {
    void prefetchOnce(queryClient, {
      queryKey: bookingFormQueryKey(tripInstanceId, bookingId),
      queryFn: () => api.bookingForm(tripInstanceId, bookingId),
    });
  }

  function prefetchBookingCreateFlow(tripInstanceId: string) {
    prefetchBookingPanel(tripInstanceId);
    prefetchBookingForm(tripInstanceId);
  }

  function prefetchTrackerPanel(tripInstanceId: string) {
    void prefetchOnce(queryClient, {
      queryKey: trackerPanelQueryKey(tripInstanceId),
      queryFn: () => api.trackerPanel(tripInstanceId),
    });
  }

  function openPanel(
    nextPanel: "bookings" | "trackers",
    tripInstanceId: string,
    mode: "list" | "create" | "edit" = "list",
    bookingId = "",
  ) {
    const next = new URLSearchParams(searchParams);
    next.set("panel", nextPanel);
    next.set("trip_instance_id", tripInstanceId);
    next.delete("booking_mode");
    next.delete("booking_id");
    setSearchParams(next, { replace: false });
    if (nextPanel === "bookings") {
      setBookingPanelState({ mode, bookingId });
    }
  }

  function closePanel() {
    const next = new URLSearchParams(searchParams);
    next.delete("panel");
    next.delete("trip_instance_id");
    next.delete("booking_mode");
    next.delete("booking_id");
    setSearchParams(next, { replace: false });
  }

  function changeBookingMode(mode: "list" | "create" | "edit", bookingId = "") {
    setBookingPanelState({ mode, bookingId });
  }

  const currentTripRow = panelTripInstanceId ? visibleTripRows.get(panelTripInstanceId) : undefined;
  const initialBookingPanel = panel === "bookings" ? bookingPanelPreview(currentTripRow) : null;
  const initialTrackerPanel = panel === "trackers" ? trackerPanelPreview(currentTripRow) : null;
  const showingDesktopInspector = useDesktopInspector && !!panelTripInstanceId && (panel === "bookings" || panel === "trackers");

  async function handleDeleteTrip(row: TripRowValue) {
    const confirmation = row.trip.delete?.confirmation;
    if (!confirmation) {
      return;
    }
    const approved = await confirm({
      title: confirmation.title,
      description: confirmation.description,
      actionLabel: "Delete trip",
      cancelLabel: "Keep trip",
      tone: "danger",
    });
    if (!approved) {
      return;
    }
    try {
      await deleteTripMutation.mutateAsync(row.trip.tripInstanceId);
    } catch {
      // error toast + rollback are handled by the mutation lifecycle
    }
  }

  async function handleLinkUnmatchedBooking(unmatchedBookingId: string, tripInstanceId: string) {
    try {
      await unmatchedMutation.mutateAsync({ unmatchedBookingId, tripInstanceId, kind: "link" });
      pushToast({ message: "Booking linked" });
    } catch {
      // error toast + rollback are handled by the mutation lifecycle
    }
  }

  async function handleDeleteUnmatchedBooking(unmatchedBookingId: string) {
    const approved = await confirm({
      title: "Delete this booking?",
      description: "It will be removed from needs linking.",
      actionLabel: "Delete booking",
      cancelLabel: "Keep booking",
      tone: "danger",
    });
    if (!approved) {
      return;
    }
    try {
      await unmatchedMutation.mutateAsync({ unmatchedBookingId, kind: "delete" });
      pushToast({ message: "Booking deleted" });
    } catch {
      // error toast + rollback are handled by the mutation lifecycle
    }
  }

  function handleEditUnmatchedBooking(unmatchedBookingId: string) {
    setEditingUnmatchedBookingId(unmatchedBookingId);
  }

  return (
    <div className={`app-shell${showingDesktopInspector ? " app-shell--with-inspector" : ""}`}>
      <div className={`dashboard-workbench${showingDesktopInspector ? " dashboard-workbench--with-inspector" : ""}`}>
        <div className="dashboard-workbench__main">
          <header className="page-header">
            <div>
              <p className="page-header__eyebrow">Milemark</p>
              <h1>Travel dashboard</h1>
            </div>
            <div className="page-header__stats">
              <div>
                <span>Upcoming</span>
                <strong>{dashboardQuery.data?.counts.totalUpcoming ?? "—"}</strong>
              </div>
              <div>
                <span>Booked</span>
                <strong>{dashboardQuery.data?.counts.totalBooked ?? "—"}</strong>
              </div>
            </div>
          </header>
          <main className="dashboard-layout">
            {dashboardQuery.data ? (
              dashboardQuery.data.actionItems.length ? (
                <ActionItemsSection
                  items={dashboardQuery.data.actionItems}
                  onOpenBookings={(tripInstanceId, mode, rowBookingId) => openPanel("bookings", tripInstanceId, mode, rowBookingId)}
                  onOpenTrackers={(tripInstanceId) => openPanel("trackers", tripInstanceId)}
                  onDeleteTrip={handleDeleteTrip}
                  activeTripInstanceId={panelTripInstanceId}
                  onLinkUnmatchedBooking={handleLinkUnmatchedBooking}
                  onEditUnmatchedBooking={handleEditUnmatchedBooking}
                  onDeleteUnmatchedBooking={handleDeleteUnmatchedBooking}
                  onPrefetchBookings={prefetchBookingPanel}
                  onPrefetchCreateBooking={prefetchBookingCreateFlow}
                  onPrefetchTrackers={prefetchTrackerPanel}
                />
              ) : null
            ) : dashboardQuery.isError ? (
              <section className="surface">
                <article className="quiet-state-card">
                  <strong>Unable to load dashboard.</strong>
                  <p>{dashboardQuery.error instanceof Error ? dashboardQuery.error.message : "Try again in a moment."}</p>
                  <div className="quiet-state-card__actions">
                    <button type="button" className="secondary-button" onClick={() => void dashboardQuery.refetch()}>
                      Retry
                    </button>
                  </div>
                </article>
              </section>
            ) : null}

            <section className="surface" id="dashboard-groups">
              <div className="surface__header">
                <h2>Collections</h2>
                {collectionEditor?.mode !== "create" ? (
                  <button type="button" className="primary-button" onClick={startCreateCollection}>
                    Create collection
                  </button>
                ) : (
                  <span className="primary-button surface__header-action-placeholder" aria-hidden="true">
                    Create collection
                  </span>
                )}
              </div>
              <div className="collection-board-react">
                {collectionEditor?.mode === "create" ? (
                  <CollectionNameEditor
                    mode="create"
                    variant="card"
                    onCancel={stopCollectionEditing}
                    onSave={(label) => collectionMutation.mutateAsync({ label })}
                  />
                ) : null}
                {dashboardQuery.data?.collections.map((collection: CollectionCardValue) => (
                  <CollectionCard
                    key={collection.groupId}
                    collection={collection}
                    editing={collectionEditor?.mode === "edit" && collectionEditor.groupId === collection.groupId}
                    onEdit={() => startEditCollection(collection.groupId)}
                    onDelete={() => void handleDeleteCollection(collection.groupId, collection.label)}
                    onCancelEdit={stopCollectionEditing}
                    onSaveEdit={(label) => collectionMutation.mutateAsync({ label, groupId: collection.groupId })}
                    onToggleRecurringTrip={(tripId, active) => toggleTripMutation.mutate({ tripId, active })}
                    pendingRecurringTripId={toggleTripMutation.isPending ? (toggleTripMutation.variables?.tripId ?? "") : ""}
                  />
                ))}
              </div>
            </section>

            <section className="surface" id="all-travel">
              <div className="surface__header">
                <h2>Trips</h2>
                <PrefetchLink
                  className="primary-button"
                  to="/trips/new"
                  onPrefetch={() => void prefetchTripEditorFromHref(queryClient, "/trips/new")}
                >
                  Create trip
                </PrefetchLink>
              </div>
              {dashboardQuery.data ? (
                <>
                  <FilterBar
                    options={dashboardQuery.data.filters.groupOptions}
                    selected={dashboardQuery.data.filters.selectedTripGroupIds}
                    includeBooked={dashboardQuery.data.filters.includeBooked}
                    onToggleOption={toggleGroupFilter}
                    onToggleBooked={toggleBookedFilter}
                  />
                  <div className="trip-list">
                    {dashboardQuery.data.trips.map((row) => (
                      <TripRow
                        key={row.trip.tripInstanceId}
                        row={row}
                        onOpenBookings={(tripInstanceId, mode, rowBookingId) => openPanel("bookings", tripInstanceId, mode, rowBookingId)}
                        onOpenTrackers={(tripInstanceId) => openPanel("trackers", tripInstanceId)}
                        onDelete={handleDeleteTrip}
                        isActive={panelTripInstanceId === row.trip.tripInstanceId}
                        onPrefetchBookings={prefetchBookingPanel}
                        onPrefetchCreateBooking={prefetchBookingCreateFlow}
                        onPrefetchTrackers={prefetchTrackerPanel}
                      />
                    ))}
                  </div>
                </>
              ) : dashboardQuery.isError ? (
                <article className="quiet-state-card">
                  <strong>Unable to load trips.</strong>
                  <p>{dashboardQuery.error instanceof Error ? dashboardQuery.error.message : "Try again in a moment."}</p>
                  <div className="quiet-state-card__actions">
                    <button type="button" className="secondary-button" onClick={() => void dashboardQuery.refetch()}>
                      Retry
                    </button>
                  </div>
                </article>
              ) : (
                <div className="surface-loading">Loading trips…</div>
              )}
            </section>
          </main>
        </div>
        {showingDesktopInspector ? (
          <InspectorShell title={panel === "bookings" ? "Bookings" : "Trackers"} onClose={closePanel}>
            {panel === "bookings" ? (
              <BookingInspector
                tripInstanceId={panelTripInstanceId}
                initialPanel={initialBookingPanel}
                dashboardFilters={dashboardFilters}
                onRefreshDashboard={refreshCurrentDashboard}
                onChangeMode={changeBookingMode}
              />
            ) : (
              <TrackerInspector tripInstanceId={panelTripInstanceId} initialPanel={initialTrackerPanel} />
            )}
          </InspectorShell>
        ) : null}
      </div>

      {!showingDesktopInspector && panel === "bookings" && panelTripInstanceId ? (
        <BookingPanel
          tripInstanceId={panelTripInstanceId}
          mode={bookingPanelState.mode}
          bookingId={bookingPanelState.bookingId}
          initialPanel={initialBookingPanel}
          dashboardFilters={dashboardFilters}
          onClose={closePanel}
          onRefreshDashboard={refreshCurrentDashboard}
          onChangeMode={changeBookingMode}
        />
      ) : null}
      {!showingDesktopInspector && panel === "trackers" && panelTripInstanceId ? (
        <TrackerPanel tripInstanceId={panelTripInstanceId} initialPanel={initialTrackerPanel} onClose={closePanel} />
      ) : null}
      {showingDesktopInspector && panel === "bookings" && panelTripInstanceId && bookingPanelState.mode !== "list" ? (
        <BookingFormModal
          tripInstanceId={panelTripInstanceId}
          mode={bookingPanelState.mode}
          bookingId={bookingPanelState.bookingId}
          dashboardFilters={dashboardFilters}
          onClose={() => changeBookingMode("list")}
          onRefreshDashboard={refreshCurrentDashboard}
        />
      ) : null}
      {editingUnmatchedBookingId ? (
        <UnmatchedBookingEditorModal
          unmatchedBookingId={editingUnmatchedBookingId}
          dashboardFilters={dashboardFilters}
          onClose={() => setEditingUnmatchedBookingId("")}
          onRefreshDashboard={refreshCurrentDashboard}
        />
      ) : null}
    </div>
  );
}
