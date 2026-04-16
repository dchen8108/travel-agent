import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import type { CollectionCard as CollectionCardValue, TripRow as TripRowValue } from "../types";
import { CollectionCard } from "../components/CollectionCard";
import { CollectionEditorCard } from "../components/CollectionEditorCard";
import { BookingPanel } from "../components/BookingPanel";
import { FilterBar } from "../components/FilterBar";
import { TrackerPanel } from "../components/TrackerPanel";
import { TripRow } from "../components/TripRow";

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [editingCollectionId, setEditingCollectionId] = useState("");
  const queryClient = useQueryClient();

  const selectedTripGroupIds = searchParams.getAll("trip_group_id");
  const includeBooked = searchParams.get("include_booked") !== "false";

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
  });

  const collectionMutation = useMutation({
    mutationFn: async ({ label, groupId }: { label: string; groupId?: string }) => (
      groupId ? api.updateCollection(groupId, label) : api.createCollection(label)
    ),
    onSuccess: async () => {
      setCreatingCollection(false);
      setEditingCollectionId("");
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const toggleTripMutation = useMutation({
    mutationFn: ({ tripId, active }: { tripId: string; active: boolean }) => api.toggleRecurringTrip(tripId, active),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const deleteTripMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.deleteTripInstance(tripInstanceId),
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

  function toggleBookedFilter() {
    const next = new URLSearchParams(searchParams);
    if (includeBooked) {
      next.set("include_booked", "false");
    } else {
      next.delete("include_booked");
    }
    setSearchParams(next, { replace: true });
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

      <main className="dashboard-layout">
        <section className="surface">
          <div className="surface__header">
            <h2>Collections</h2>
            {!creatingCollection ? (
              <button type="button" className="primary-button" onClick={() => setCreatingCollection(true)}>
                Create collection
              </button>
            ) : null}
          </div>
          <div className="collection-board-react">
            {creatingCollection ? (
              <CollectionEditorCard
                mode="create"
                onCancel={() => setCreatingCollection(false)}
                onSave={(label) => collectionMutation.mutateAsync({ label })}
              />
            ) : null}
            {dashboardQuery.data?.collections.map((collection: CollectionCardValue) => (
              editingCollectionId === collection.groupId ? (
                <CollectionEditorCard
                  key={collection.groupId}
                  mode="edit"
                  initialLabel={collection.label}
                  onCancel={() => setEditingCollectionId("")}
                  onSave={(label) => collectionMutation.mutateAsync({ label, groupId: collection.groupId })}
                />
              ) : (
                <CollectionCard
                  key={collection.groupId}
                  collection={collection}
                  onEdit={() => setEditingCollectionId(collection.groupId)}
                  onToggleRecurringTrip={(tripId, active) => toggleTripMutation.mutate({ tripId, active })}
                />
              )
            ))}
          </div>
        </section>

        <section className="surface">
          <div className="surface__header">
            <h2>Trips</h2>
            <a className="primary-button" href="/trips/new">Create trip</a>
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
