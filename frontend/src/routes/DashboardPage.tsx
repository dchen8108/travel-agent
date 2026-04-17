import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ActionItemsSection } from "../components/ActionItemsSection";
import { BookingPanel } from "../components/BookingPanel";
import { CollectionCard } from "../components/CollectionCard";
import { CollectionEditorCard } from "../components/CollectionEditorCard";
import { useConfirm } from "../components/ConfirmProvider";
import { FilterBar } from "../components/FilterBar";
import { PrefetchLink } from "../components/PrefetchLink";
import { TrackerPanel } from "../components/TrackerPanel";
import { TripRow } from "../components/TripRow";
import { useToast } from "../components/ToastProvider";
import { api } from "../lib/api";
import { bookingFormQueryKey, bookingPanelQueryKey, dashboardQueryKey, trackerPanelQueryKey } from "../lib/queryKeys";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import type { CollectionCard as CollectionCardValue, DashboardPayload, TripRow as TripRowValue } from "../types";

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
    placeholderData: (previous) => previous,
  });

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
    if (panel === "bookings" && panelTripInstanceId) {
      setBookingPanelState(initialBookingPanelState(searchParams));
      return;
    }
    setBookingPanelState({ mode: "list", bookingId: "" });
  }, [panel, panelTripInstanceId, searchParams]);

  function replaceCurrentDashboard(next: DashboardPayload) {
    queryClient.setQueryData(dashboardQueryKey(dashboardQueryString), next);
    void queryClient.invalidateQueries({ queryKey: ["dashboard"], refetchType: "inactive" });
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

  const toggleTripMutation = useMutation({
    mutationFn: ({ tripId, active }: { tripId: string; active: boolean }) => api.toggleRecurringTrip(tripId, active, dashboardFilters),
    onSuccess: ({ dashboard }) => {
      replaceCurrentDashboard(dashboard);
    },
  });

  const deleteTripMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.deleteTripInstance(tripInstanceId, dashboardFilters),
    onSuccess: ({ dashboard }) => {
      replaceCurrentDashboard(dashboard);
      pushToast({ message: "Trip deleted" });
    },
  });

  const unmatchedMutation = useMutation({
    mutationFn: ({
      unmatchedBookingId,
      tripInstanceId,
      kind,
    }: {
      unmatchedBookingId: string;
      tripInstanceId?: string;
      kind: "link" | "delete";
    }) => {
      if (kind === "delete") {
        return api.deleteBooking(unmatchedBookingId, dashboardFilters);
      }
      if (!tripInstanceId) {
        throw new Error("Choose a scheduled trip.");
      }
      return api.linkUnmatchedBooking(unmatchedBookingId, tripInstanceId, dashboardFilters);
    },
    onSuccess: ({ dashboard }) => {
      replaceCurrentDashboard(dashboard);
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
    queryClient.prefetchQuery({
      queryKey: bookingPanelQueryKey(tripInstanceId),
      queryFn: () => api.bookingPanel(tripInstanceId),
    });
    queryClient.prefetchQuery({
      queryKey: bookingFormQueryKey(tripInstanceId),
      queryFn: () => api.bookingForm(tripInstanceId),
    });
  }

  function prefetchTrackerPanel(tripInstanceId: string) {
    queryClient.prefetchQuery({
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
    setBookingPanelState({ mode: "list", bookingId: "" });
  }

  function changeBookingMode(mode: "list" | "create" | "edit", bookingId = "") {
    setBookingPanelState({ mode, bookingId });
  }

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
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to delete trip."), kind: "error" });
    }
  }

  async function handleLinkUnmatchedBooking(unmatchedBookingId: string, tripInstanceId: string) {
    try {
      await unmatchedMutation.mutateAsync({ unmatchedBookingId, tripInstanceId, kind: "link" });
      pushToast({ message: "Booking linked" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to link booking."), kind: "error" });
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
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to delete booking."), kind: "error" });
    }
  }

  return (
    <div className="app-shell">
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
          <ActionItemsSection
            items={dashboardQuery.data.actionItems}
            onOpenBookings={(tripInstanceId, mode, rowBookingId) => openPanel("bookings", tripInstanceId, mode, rowBookingId)}
            onOpenTrackers={(tripInstanceId) => openPanel("trackers", tripInstanceId)}
            onDeleteTrip={handleDeleteTrip}
            onLinkUnmatchedBooking={handleLinkUnmatchedBooking}
            onDeleteUnmatchedBooking={handleDeleteUnmatchedBooking}
            onPrefetchBookings={prefetchBookingPanel}
            onPrefetchTrackers={prefetchTrackerPanel}
          />
        ) : null}

        <section className="surface" id="dashboard-groups">
          <div className="surface__header">
            <h2>Collections</h2>
            {collectionEditor?.mode !== "create" ? (
              <button type="button" className="primary-button" onClick={startCreateCollection}>
                Create collection
              </button>
            ) : null}
          </div>
          <div className="collection-board-react">
            {collectionEditor?.mode === "create" ? (
              <CollectionEditorCard
                mode="create"
                onCancel={stopCollectionEditing}
                onSave={(label) => collectionMutation.mutateAsync({ label })}
              />
            ) : null}
            {dashboardQuery.data?.collections.map((collection: CollectionCardValue) => (
              collectionEditor?.mode === "edit" && collectionEditor.groupId === collection.groupId ? (
                <CollectionEditorCard
                  key={collection.groupId}
                  collectionId={collection.groupId}
                  mode="edit"
                  initialLabel={collection.label}
                  onCancel={stopCollectionEditing}
                  onSave={(label) => collectionMutation.mutateAsync({ label, groupId: collection.groupId })}
                />
              ) : (
                <CollectionCard
                  key={collection.groupId}
                  collection={collection}
                  onEdit={() => startEditCollection(collection.groupId)}
                  onToggleRecurringTrip={(tripId, active) => toggleTripMutation.mutate({ tripId, active })}
                />
              )
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
                    onPrefetchBookings={prefetchBookingPanel}
                    onPrefetchTrackers={prefetchTrackerPanel}
                  />
                ))}
              </div>
            </>
          ) : (
            <div className="surface-loading">Loading trips…</div>
          )}
        </section>
      </main>

      {panel === "bookings" && panelTripInstanceId ? (
        <BookingPanel
          tripInstanceId={panelTripInstanceId}
          mode={bookingPanelState.mode}
          bookingId={bookingPanelState.bookingId}
          dashboardFilters={dashboardFilters}
          onClose={closePanel}
          onReplaceDashboard={replaceCurrentDashboard}
          onChangeMode={changeBookingMode}
        />
      ) : null}
      {panel === "trackers" && panelTripInstanceId ? (
        <TrackerPanel tripInstanceId={panelTripInstanceId} onClose={closePanel} />
      ) : null}
    </div>
  );
}
