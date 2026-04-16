import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import type { CollectionCard as CollectionCardValue, DashboardPayload, TripRow as TripRowValue } from "../types";
import { ActionItemsSection } from "../components/ActionItemsSection";
import { CollectionCard } from "../components/CollectionCard";
import { CollectionEditorCard } from "../components/CollectionEditorCard";
import { BookingPanel } from "../components/BookingPanel";
import { FilterBar } from "../components/FilterBar";
import { TrackerPanel } from "../components/TrackerPanel";
import { TripRow } from "../components/TripRow";
import { IconButton } from "../components/IconButton";
import { CloseIcon } from "../components/Icons";
import { PrefetchLink } from "../components/PrefetchLink";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [collectionEditor, setCollectionEditor] = useState<{ mode: "create" | "edit"; groupId?: string } | null>(() => {
    if (searchParams.get("create_group") === "1") {
      return { mode: "create" };
    }
    const groupId = searchParams.get("edit_group_id") ?? "";
    return groupId ? { mode: "edit", groupId } : null;
  });

  const selectedTripGroupIds = searchParams.getAll("trip_group_id");
  const includeBooked = searchParams.get("include_booked") !== "false";
  const flashMessage = searchParams.get("message") ?? "";
  const flashMessageKind = searchParams.get("message_kind") ?? "success";

  const dashboardFilters = useMemo(() => {
    const params = new URLSearchParams();
    for (const value of selectedTripGroupIds) {
      params.append("trip_group_id", value);
    }
    if (!includeBooked) {
      params.set("include_booked", "false");
    }
    return params;
  }, [includeBooked, selectedTripGroupIds]);

  const dashboardQuery = useQuery({
    queryKey: ["dashboard", dashboardFilters.toString()],
    queryFn: () => api.dashboard(dashboardFilters),
    placeholderData: (previous) => previous,
  });

  const collectionMutation = useMutation({
    mutationFn: async ({ label, groupId }: { label: string; groupId?: string }) => (
      groupId ? api.updateCollection(groupId, label) : api.createCollection(label)
    ),
    onSuccess: (collection) => {
      setCollectionEditor(null);
      clearCollectionEditorParams();
      queryClient.setQueriesData<DashboardPayload>({ queryKey: ["dashboard"] }, (current) => {
        if (!current) {
          return current;
        }
        const existingIndex = current.collections.findIndex((item) => item.groupId === collection.groupId);
        const collections = [...current.collections];
        if (existingIndex >= 0) {
          collections[existingIndex] = collection;
        } else {
          collections.unshift(collection);
        }
        return { ...current, collections };
      });
    },
  });

  const toggleTripMutation = useMutation({
    mutationFn: ({ tripId, active }: { tripId: string; active: boolean }) => api.toggleRecurringTrip(tripId, active),
    onSuccess: (result) => {
      queryClient.setQueriesData<DashboardPayload>({ queryKey: ["dashboard"] }, (current) => (
        current ? { ...current, collections: result.collections } : current
      ));
    },
  });

  const deleteTripMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.deleteTripInstance(tripInstanceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const unmatchedMutation = useMutation({
    mutationFn: async ({
      unmatchedBookingId,
      tripInstanceId,
      kind,
    }: {
      unmatchedBookingId: string;
      tripInstanceId?: string;
      kind: "link" | "delete";
    }) => {
      if (kind === "delete") {
        await api.deleteBooking(unmatchedBookingId);
        return;
      }
      if (!tripInstanceId) {
        throw new Error("Choose a scheduled trip.");
      }
      await api.linkUnmatchedBooking(unmatchedBookingId, tripInstanceId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
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

  function dismissMessage() {
    const next = new URLSearchParams(searchParams);
    next.delete("message");
    next.delete("message_kind");
    setSearchParams(next, { replace: true });
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
      queryKey: ["booking-panel", tripInstanceId],
      queryFn: () => api.bookingPanel(tripInstanceId, "list"),
    });
  }

  function prefetchTrackerPanel(tripInstanceId: string) {
    queryClient.prefetchQuery({
      queryKey: ["tracker-panel", tripInstanceId],
      queryFn: () => api.trackerPanel(tripInstanceId),
    });
  }

  function openPanel(panel: "bookings" | "trackers", tripInstanceId: string, mode = "list", bookingId = "") {
    const next = new URLSearchParams(searchParams);
    next.set("panel", panel);
    next.set("trip_instance_id", tripInstanceId);
    if (panel === "bookings") {
      if (mode !== "list") {
        next.set("booking_mode", mode);
      } else {
        next.delete("booking_mode");
      }
      if (bookingId) {
        next.set("booking_id", bookingId);
      } else {
        next.delete("booking_id");
      }
    } else {
      next.delete("booking_mode");
      next.delete("booking_id");
    }
    setSearchParams(next, { replace: false });
  }

  function closePanel() {
    const next = new URLSearchParams(searchParams);
    next.delete("panel");
    next.delete("trip_instance_id");
    next.delete("booking_mode");
    next.delete("booking_id");
    setSearchParams(next, { replace: false });
  }

  async function handleDeleteTrip(row: TripRowValue) {
    const confirmation = row.trip.delete?.confirmation;
    if (!confirmation) {
      return;
    }
    if (!window.confirm(`${confirmation.title}\n\n${confirmation.description}`)) {
      return;
    }
    await deleteTripMutation.mutateAsync(row.trip.tripInstanceId);
  }

  async function handleLinkUnmatchedBooking(unmatchedBookingId: string, tripInstanceId: string) {
    await unmatchedMutation.mutateAsync({ unmatchedBookingId, tripInstanceId, kind: "link" });
  }

  async function handleDeleteUnmatchedBooking(unmatchedBookingId: string) {
    if (!window.confirm("Delete this booking?")) {
      return;
    }
    await unmatchedMutation.mutateAsync({ unmatchedBookingId, kind: "delete" });
  }

  const panel = searchParams.get("panel");
  const panelTripInstanceId = searchParams.get("trip_instance_id") ?? "";
  const bookingMode = (searchParams.get("booking_mode") as "list" | "create" | "edit" | null) ?? "list";
  const bookingId = searchParams.get("booking_id") ?? "";

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

      {flashMessage ? (
        <div className={`flash-banner flash-banner--${flashMessageKind}`}>
          <span>{flashMessage}</span>
          <IconButton label="Dismiss message" onClick={dismissMessage}>
            <CloseIcon />
          </IconButton>
        </div>
      ) : null}

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
          mode={bookingMode}
          bookingId={bookingId}
          onClose={closePanel}
          onChangeMode={(nextMode, nextBookingId) => openPanel("bookings", panelTripInstanceId, nextMode, nextBookingId)}
        />
      ) : null}
      {panel === "trackers" && panelTripInstanceId ? (
        <TrackerPanel tripInstanceId={panelTripInstanceId} onClose={closePanel} />
      ) : null}
    </div>
  );
}
