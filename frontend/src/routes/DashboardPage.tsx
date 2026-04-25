import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ActionItemsSection } from "../components/ActionItemsSection";
import { AddIcon } from "../components/Icons";
import { BookingFormModal } from "../components/BookingFormModal";
import { BookingInspector } from "../components/BookingInspector";
import { CollectionCard } from "../components/CollectionCard";
import { CollectionNameEditor } from "../components/CollectionNameEditor";
import { useConfirm } from "../components/ConfirmProvider";
import { FilterBar } from "../components/FilterBar";
import { IconButton } from "../components/IconButton";
import { InspectorShell } from "../components/InspectorShell";
import { Modal } from "../components/Modal";
import { PrefetchLink } from "../components/PrefetchLink";
import { TrackerInspector } from "../components/TrackerInspector";
import { TripRow } from "../components/TripRow";
import { UnmatchedBookingEditorModal } from "../components/UnmatchedBookingEditorModal";
import { useToast } from "../components/ToastProvider";
import { api } from "../lib/api";
import {
  buildDashboardFilters,
  DASHBOARD_PARAM_KEYS,
  parseDashboardUrlState,
} from "../lib/dashboardUrlState";
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

function filteredTripRows(
  dashboard: DashboardPayload | undefined,
  {
    selectedTripGroupIds,
    includeBooked,
    includeSkipped,
  }: {
    selectedTripGroupIds: string[];
    includeBooked: boolean;
    includeSkipped: boolean;
  },
) {
  if (!dashboard) {
    return [];
  }
  const selectedIds = new Set(selectedTripGroupIds);
  const includeUngrouped = selectedIds.has("__ungrouped__");
  const groupedSelections = new Set([...selectedIds].filter((value) => value !== "__ungrouped__"));

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
    const matchingGroups = dashboard.collections
      .filter((collection) => collection.upcomingTrips.some((trip) => trip.tripInstanceId === row.trip.tripInstanceId))
      .map((collection) => collection.groupId);
    if (matchingGroups.length === 0) {
      return includeUngrouped;
    }
    return matchingGroups.some((groupId) => groupedSelections.has(groupId));
  });
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
  const previewRows = row.currentOffer && !row.currentOffer.priceIsStatus
    ? [
        {
          rowId: "",
          travelDate: row.trip.anchorDate,
          offer: row.currentOffer,
        },
      ]
    : [];
  return {
    trip: row.trip,
    rows: previewRows,
    lastRefreshLabel: "",
    tripAnchorDate: row.trip.anchorDate,
    emptyLabel: row.currentOffer?.statusKind === "unavailable" ? "No live fares right now." : "Checking live fares…",
  };
}

function desktopInspectorPreferred() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(min-width: 2000px)").matches;
}

export function DashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { confirm } = useConfirm();
  const [editingUnmatchedBookingId, setEditingUnmatchedBookingId] = useState("");
  const [useDesktopInspector, setUseDesktopInspector] = useState(() => desktopInspectorPreferred());

  const {
    panel,
    panelTripInstanceId,
    collectionEditor,
    bookingPanelState,
    selectedTripGroupIds,
    includeBooked,
    includeSkipped,
  } =
    useMemo(() => parseDashboardUrlState(searchParams), [searchParams]);

  const dashboardFilters = useMemo(() => {
    return buildDashboardFilters(selectedTripGroupIds, includeBooked, includeSkipped);
  }, [includeBooked, includeSkipped, selectedTripGroupIds]);
  const dashboardCacheKey = dashboardQueryKey("all");

  const dashboardQuery = useQuery({
    queryKey: dashboardCacheKey,
    queryFn: () => api.dashboard(),
  });
  const displayTrips = useMemo(
    () => filteredTripRows(dashboardQuery.data, { selectedTripGroupIds, includeBooked, includeSkipped }),
    [dashboardQuery.data, includeBooked, includeSkipped, selectedTripGroupIds],
  );
  const visibleTripRows = useMemo(
    () => tripRowLookup(dashboardQuery.data ? { ...dashboardQuery.data, trips: displayTrips } : undefined),
    [dashboardQuery.data, displayTrips],
  );

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
    const message = searchParams.get(DASHBOARD_PARAM_KEYS.message);
    if (!message) {
      return;
    }
    pushToast({
      message,
      kind: searchParams.get(DASHBOARD_PARAM_KEYS.messageKind) === "error" ? "error" : "success",
    });
    const next = new URLSearchParams(searchParams);
    next.delete(DASHBOARD_PARAM_KEYS.message);
    next.delete(DASHBOARD_PARAM_KEYS.messageKind);
    setSearchParams(next, { replace: true });
  }, [pushToast, searchParams, setSearchParams]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const inspectorMediaQuery = window.matchMedia("(min-width: 2000px)");
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
    queryClient.setQueryData(dashboardCacheKey, next);
    void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
  }

  function updateDashboardSearchParams(
    mutate: (next: URLSearchParams) => void,
    options: { replace?: boolean } = {},
  ) {
    const next = new URLSearchParams(searchParams);
    mutate(next);
    setSearchParams(next, { replace: options.replace ?? false });
  }

  async function refreshCurrentDashboard() {
    await queryClient.invalidateQueries({ queryKey: dashboardCacheKey });
  }

  async function handleBookingPanelResult(tripInstanceId: string, panel: BookingPanelPayload | null) {
    if (panel) {
      queryClient.setQueryData(bookingPanelQueryKey(tripInstanceId), panel);
    } else {
      queryClient.removeQueries({ queryKey: bookingPanelQueryKey(tripInstanceId), exact: true });
    }
    await refreshCurrentDashboard();
    if (panelTripInstanceId === tripInstanceId) {
      if (!panel || panel.rows.length <= 1) {
        closePanel();
      } else {
        changeBookingMode("list");
      }
    }
  }

  const collectionMutation = useMutation({
    mutationFn: async ({ label, groupId }: { label: string; groupId?: string }) => (
      groupId ? api.updateCollection(groupId, label) : api.createCollection(label)
    ),
    onSuccess: ({ dashboard }) => {
      clearCollectionEditorParams();
      replaceCurrentDashboard(dashboard);
      pushToast({ message: "Collection saved" });
    },
  });

  const deleteCollectionMutation = useMutation({
    mutationFn: (groupId: string) => api.deleteCollection(groupId),
    onMutate: async (groupId) => {
      await queryClient.cancelQueries({ queryKey: dashboardCacheKey });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardCacheKey);
      if (previous) {
        queryClient.setQueryData(
          dashboardCacheKey,
          optimisticRemoveCollection(previous, groupId),
        );
      }
      return { previous };
    },
    onError: (error, _groupId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardCacheKey, context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to delete collection."), kind: "error" });
    },
    onSuccess: (_result, groupId) => {
      if (selectedTripGroupIds.includes(groupId) || (collectionEditor?.mode === "edit" && collectionEditor.groupId === groupId)) {
        updateDashboardSearchParams((next) => {
          if (selectedTripGroupIds.includes(groupId)) {
            const remaining = next.getAll(DASHBOARD_PARAM_KEYS.tripGroupId).filter((value) => value !== groupId);
            next.delete(DASHBOARD_PARAM_KEYS.tripGroupId);
            remaining.forEach((value) => next.append(DASHBOARD_PARAM_KEYS.tripGroupId, value));
          }
          if (collectionEditor?.mode === "edit" && collectionEditor.groupId === groupId) {
            next.delete(DASHBOARD_PARAM_KEYS.createCollection);
            next.delete(DASHBOARD_PARAM_KEYS.editCollectionId);
          }
        }, { replace: true });
      }
      void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
      pushToast({ message: "Collection deleted" });
    },
  });

  const toggleTripMutation = useMutation({
    mutationFn: ({ tripId, active }: { tripId: string; active: boolean }) => api.toggleRecurringTrip(tripId, active, dashboardFilters),
    onMutate: async ({ tripId, active }) => {
      await queryClient.cancelQueries({ queryKey: dashboardCacheKey });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardCacheKey);
      if (previous) {
        queryClient.setQueryData(
          dashboardCacheKey,
          optimisticSetRecurringTripActive(previous, tripId, active),
        );
      }
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardCacheKey, context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to update recurring trip."), kind: "error" });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: dashboardQueryPrefix(), refetchType: "inactive" });
    },
  });

  const deleteTripMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.deleteTripInstance(tripInstanceId),
    onMutate: async (tripInstanceId) => {
      await queryClient.cancelQueries({ queryKey: dashboardCacheKey });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardCacheKey);
      if (previous) {
        queryClient.setQueryData(
          dashboardCacheKey,
          optimisticRemoveTripInstance(previous, tripInstanceId),
        );
      }
      return { previous };
    },
    onError: (error, _tripInstanceId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardCacheKey, context.previous);
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

  const skipTripMutation = useMutation({
    mutationFn: ({ tripInstanceId, skipped }: { tripInstanceId: string; skipped: boolean }) => (
      api.setTripSkipped(tripInstanceId, skipped)
    ),
    onSuccess: ({ dashboard }, { tripInstanceId, skipped }) => {
      replaceCurrentDashboard(dashboard);
      if (!dashboard.trips.some((row) => row.trip.tripInstanceId === tripInstanceId) && panelTripInstanceId === tripInstanceId) {
        closePanel();
      }
      pushToast({ message: skipped ? "Trip skipped" : "Trip unskipped" });
    },
    onError: (error, { skipped }) => {
      pushToast({
        message: errorMessage(error, skipped ? "Unable to skip trip." : "Unable to unskip trip."),
        kind: "error",
      });
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
      await queryClient.cancelQueries({ queryKey: dashboardCacheKey });
      const previous = queryClient.getQueryData<DashboardPayload>(dashboardCacheKey);
      if (previous) {
        queryClient.setQueryData(
          dashboardCacheKey,
          optimisticRemoveUnmatchedBooking(previous, unmatchedBookingId),
        );
      }
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(dashboardCacheKey, context.previous);
      }
      pushToast({ message: errorMessage(error, "Unable to update booking."), kind: "error" });
    },
    onSuccess: () => {
      refreshCurrentDashboard();
    },
  });

  function toggleGroupFilter(groupId: string) {
    updateDashboardSearchParams((next) => {
      const current = new Set(next.getAll(DASHBOARD_PARAM_KEYS.tripGroupId));
      if (current.has(groupId)) {
        current.delete(groupId);
      } else {
        current.add(groupId);
      }
      next.delete(DASHBOARD_PARAM_KEYS.tripGroupId);
      [...current].forEach((value) => next.append(DASHBOARD_PARAM_KEYS.tripGroupId, value));
    }, { replace: true });
  }

  function clearCollectionEditorParams() {
    if (!collectionEditor) {
      return;
    }
    updateDashboardSearchParams((next) => {
      next.delete(DASHBOARD_PARAM_KEYS.createCollection);
      next.delete(DASHBOARD_PARAM_KEYS.editCollectionId);
    }, { replace: true });
  }

  function startCreateCollection() {
    updateDashboardSearchParams((next) => {
      next.set(DASHBOARD_PARAM_KEYS.createCollection, "1");
      next.delete(DASHBOARD_PARAM_KEYS.editCollectionId);
    }, { replace: true });
  }

  function stopCollectionEditing() {
    clearCollectionEditorParams();
  }

  function startEditCollection(groupId: string) {
    updateDashboardSearchParams((next) => {
      next.delete(DASHBOARD_PARAM_KEYS.createCollection);
      next.set(DASHBOARD_PARAM_KEYS.editCollectionId, groupId);
    }, { replace: true });
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
    updateDashboardSearchParams((next) => {
      if (includeBooked) {
        next.set(DASHBOARD_PARAM_KEYS.includeBooked, "false");
      } else {
        next.delete(DASHBOARD_PARAM_KEYS.includeBooked);
      }
    }, { replace: true });
  }

  function toggleSkippedFilter() {
    updateDashboardSearchParams((next) => {
      if (includeSkipped) {
        next.delete(DASHBOARD_PARAM_KEYS.includeSkipped);
      } else {
        next.set(DASHBOARD_PARAM_KEYS.includeSkipped, "true");
      }
    }, { replace: true });
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

  function prefetchBookingEditFlow(tripInstanceId: string, bookingId: string) {
    prefetchBookingForm(tripInstanceId, bookingId);
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
    const currentRow = visibleTripRows.get(tripInstanceId);
    if (nextPanel === "bookings" && mode === "list" && !currentRow?.actions.showBookingModal) {
      return;
    }
    updateDashboardSearchParams((next) => {
      next.set(DASHBOARD_PARAM_KEYS.panel, nextPanel);
      next.set(DASHBOARD_PARAM_KEYS.tripInstanceId, tripInstanceId);
      if (nextPanel === "bookings" && mode !== "list") {
        next.set(DASHBOARD_PARAM_KEYS.bookingMode, mode);
        if (bookingId) {
          next.set(DASHBOARD_PARAM_KEYS.bookingId, bookingId);
        } else {
          next.delete(DASHBOARD_PARAM_KEYS.bookingId);
        }
      } else {
        next.delete(DASHBOARD_PARAM_KEYS.bookingMode);
        next.delete(DASHBOARD_PARAM_KEYS.bookingId);
      }
    });
  }

  function closePanel() {
    updateDashboardSearchParams((next) => {
      next.delete(DASHBOARD_PARAM_KEYS.panel);
      next.delete(DASHBOARD_PARAM_KEYS.tripInstanceId);
      next.delete(DASHBOARD_PARAM_KEYS.bookingMode);
      next.delete(DASHBOARD_PARAM_KEYS.bookingId);
    });
  }

  function changeBookingMode(mode: "list" | "create" | "edit", bookingId = "") {
    const shouldShowList = panelTripInstanceId ? Boolean(visibleTripRows.get(panelTripInstanceId)?.actions.showBookingModal) : false;
    if (mode === "list" && !shouldShowList) {
      closePanel();
      return;
    }
    if (panel !== "bookings" || !panelTripInstanceId) {
      return;
    }
    updateDashboardSearchParams((next) => {
      if (mode === "list") {
        next.delete(DASHBOARD_PARAM_KEYS.bookingMode);
        next.delete(DASHBOARD_PARAM_KEYS.bookingId);
      } else {
        next.set(DASHBOARD_PARAM_KEYS.bookingMode, mode);
        if (bookingId) {
          next.set(DASHBOARD_PARAM_KEYS.bookingId, bookingId);
        } else {
          next.delete(DASHBOARD_PARAM_KEYS.bookingId);
        }
      }
    });
  }

  const currentTripRow = panelTripInstanceId ? visibleTripRows.get(panelTripInstanceId) : undefined;
  const initialBookingPanel = panel === "bookings" ? bookingPanelPreview(currentTripRow) : null;
  const initialTrackerPanel = panel === "trackers" ? trackerPanelPreview(currentTripRow) : null;
  const showingDesktopInspector = useDesktopInspector && !!panelTripInstanceId && (
    panel === "trackers"
    || (
      panel === "bookings"
      && Boolean(currentTripRow?.actions.showBookingModal)
    )
  );

  useEffect(() => {
    if (!dashboardQuery.data || !panelTripInstanceId) {
      return;
    }
    if (panel === "trackers" && !currentTripRow) {
      closePanel();
      return;
    }
    if (panel !== "bookings" || bookingPanelState.mode !== "list") {
      return;
    }
    if (!currentTripRow || !currentTripRow.actions.showBookingModal) {
      closePanel();
    }
  }, [bookingPanelState.mode, currentTripRow, dashboardQuery.data, panel, panelTripInstanceId]);

  function handleBookingFlowComplete(panelPayload: BookingPanelPayload | null) {
    if (!panelPayload || panelPayload.rows.length <= 1) {
      closePanel();
      return;
    }
    changeBookingMode("list");
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
    } catch {
      // error toast + rollback are handled by the mutation lifecycle
    }
  }

  async function handleSetSkipped(row: TripRowValue, skipped: boolean) {
    try {
      await skipTripMutation.mutateAsync({ tripInstanceId: row.trip.tripInstanceId, skipped });
    } catch {
      // error toast handled in mutation lifecycle
    }
  }

  async function handleDeleteBooking(tripInstanceId: string, bookingId: string) {
    const approved = await confirm({
      title: "Delete this booking?",
      description: "This removes it from the trip and from the app.",
      actionLabel: "Delete booking",
      cancelLabel: "Keep booking",
      tone: "danger",
    });
    if (!approved) {
      return;
    }
    try {
      const result = await api.deleteBooking(bookingId, dashboardFilters);
      await handleBookingPanelResult(tripInstanceId, result.panel);
      pushToast({ message: "Booking deleted" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to delete booking."), kind: "error" });
    }
  }

  async function handleDetachBooking(tripInstanceId: string, bookingId: string) {
    const approved = await confirm({
      title: "Detach this booking from the trip?",
      description: "It will move back to needs linking.",
      actionLabel: "Detach booking",
      cancelLabel: "Keep booking",
    });
    if (!approved) {
      return;
    }
    try {
      const result = await api.unlinkBooking(bookingId, dashboardFilters);
      await handleBookingPanelResult(tripInstanceId, result.panel);
      pushToast({ message: "Booking needs linking" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to detach booking."), kind: "error" });
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
          </header>
          <main className="dashboard-layout">
            {dashboardQuery.data ? (
              dashboardQuery.data.actionItems.length ? (
                <ActionItemsSection
                  items={dashboardQuery.data.actionItems}
                  onOpenBookings={(tripInstanceId, mode, rowBookingId) => openPanel("bookings", tripInstanceId, mode, rowBookingId)}
                  onOpenTrackers={(tripInstanceId) => openPanel("trackers", tripInstanceId)}
                  onDeleteTrip={handleDeleteTrip}
                  onSetSkipped={handleSetSkipped}
                  onDeleteBooking={handleDeleteBooking}
                  onDetachBooking={handleDetachBooking}
                  activeTripInstanceId={panelTripInstanceId}
                  onLinkUnmatchedBooking={handleLinkUnmatchedBooking}
                  onEditUnmatchedBooking={handleEditUnmatchedBooking}
                  onDeleteUnmatchedBooking={handleDeleteUnmatchedBooking}
                  onPrefetchBookings={prefetchBookingPanel}
                  onPrefetchCreateBooking={prefetchBookingCreateFlow}
                  onPrefetchEditBooking={prefetchBookingEditFlow}
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
                  <IconButton
                    label="Create collection"
                    variant="inline"
                    className="surface__header-action-button"
                    onClick={startCreateCollection}
                  >
                    <AddIcon />
                  </IconButton>
                ) : (
                  <span
                    className="icon-button icon-button--inline surface__header-action-button surface__header-action-placeholder"
                    aria-hidden="true"
                  >
                    <AddIcon />
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
                  className="icon-link icon-link--inline surface__header-action-button"
                  aria-label="Create trip"
                  title="Create trip"
                  to="/trips/new"
                  onPrefetch={() => void prefetchTripEditorFromHref(queryClient, "/trips/new")}
                >
                  <AddIcon />
                </PrefetchLink>
              </div>
              {dashboardQuery.data ? (
                <>
                  <FilterBar
                    options={dashboardQuery.data.filters.groupOptions}
                    selected={selectedTripGroupIds}
                    includeBooked={includeBooked}
                    includeSkipped={includeSkipped}
                    onToggleOption={toggleGroupFilter}
                    onToggleBooked={toggleBookedFilter}
                    onToggleSkipped={toggleSkippedFilter}
                  />
                  <div className="trip-list">
                    {displayTrips.map((row) => (
                      <TripRow
                        key={row.trip.tripInstanceId}
                        row={row}
                        onOpenBookings={(tripInstanceId, mode, rowBookingId) => openPanel("bookings", tripInstanceId, mode, rowBookingId)}
                        onOpenTrackers={(tripInstanceId) => openPanel("trackers", tripInstanceId)}
                        onDelete={handleDeleteTrip}
                        onSetSkipped={handleSetSkipped}
                        onDeleteBooking={handleDeleteBooking}
                        onDetachBooking={handleDetachBooking}
                        isActive={panelTripInstanceId === row.trip.tripInstanceId}
                        onPrefetchBookings={prefetchBookingPanel}
                        onPrefetchCreateBooking={prefetchBookingCreateFlow}
                        onPrefetchEditBooking={prefetchBookingEditFlow}
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
          <InspectorShell
            title={panel === "bookings" ? "Bookings" : "Flights"}
            onClose={closePanel}
            disableOutsideClose={(panel === "bookings" && bookingPanelState.mode !== "list") || !!editingUnmatchedBookingId}
            headerActions={panel === "bookings" ? (
              <IconButton
                label="Create booking"
                variant="inline"
                className="surface__header-action-button"
                onClick={() => changeBookingMode("create")}
              >
                <AddIcon />
              </IconButton>
            ) : null}
          >
            {panel === "bookings" ? (
              <BookingInspector
                tripInstanceId={panelTripInstanceId}
                initialPanel={initialBookingPanel}
                dashboardFilters={dashboardFilters}
                onChangeMode={changeBookingMode}
                onPanelResult={handleBookingPanelResult}
              />
            ) : (
              <TrackerInspector tripInstanceId={panelTripInstanceId} initialPanel={initialTrackerPanel} />
            )}
          </InspectorShell>
        ) : null}
      </div>

      {!showingDesktopInspector && panel === "bookings" && panelTripInstanceId ? (
        bookingPanelState.mode === "list" ? (
          <Modal title="Bookings" onClose={closePanel} size="panel">
            <BookingInspector
              tripInstanceId={panelTripInstanceId}
              initialPanel={initialBookingPanel}
              dashboardFilters={dashboardFilters}
              onChangeMode={changeBookingMode}
              onPanelResult={handleBookingPanelResult}
            />
          </Modal>
        ) : (
          <BookingFormModal
            tripInstanceId={panelTripInstanceId}
            mode={bookingPanelState.mode}
            bookingId={bookingPanelState.bookingId}
            dashboardFilters={dashboardFilters}
            onClose={() => changeBookingMode("list")}
            onComplete={handleBookingFlowComplete}
            onRefreshDashboard={refreshCurrentDashboard}
          />
        )
      ) : null}
      {!showingDesktopInspector && panel === "trackers" && panelTripInstanceId ? (
        <Modal title="Flights" onClose={closePanel} size="compact">
          <TrackerInspector tripInstanceId={panelTripInstanceId} initialPanel={initialTrackerPanel} />
        </Modal>
      ) : null}
      {showingDesktopInspector && panel === "bookings" && panelTripInstanceId && bookingPanelState.mode !== "list" ? (
        <BookingFormModal
          tripInstanceId={panelTripInstanceId}
          mode={bookingPanelState.mode}
          bookingId={bookingPanelState.bookingId}
          dashboardFilters={dashboardFilters}
          onClose={() => changeBookingMode("list")}
          onComplete={handleBookingFlowComplete}
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
