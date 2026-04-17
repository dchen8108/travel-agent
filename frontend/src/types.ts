export type OfferTone = "neutral" | "success" | "accent" | "warning";
export type OfferStatusKind = "" | "pending" | "unavailable";
export type TripAttentionKind = "overbooked" | "priceDrop" | "betterOption" | "needsBooking";
export type TripLifecycle = "planned" | "booked";

export interface DateTile {
  weekday: string;
  monthDay: string;
}

export interface Offer {
  label: string;
  detail: string;
  metaLabel: string;
  dayDeltaLabel: string;
  priceLabel: string;
  href: string;
  tone: OfferTone;
  priceIsStatus: boolean;
  statusKind: OfferStatusKind;
}

export interface TripDeleteAction {
  kind: "generated" | "trip";
  confirmation: {
    title: string;
    description: string;
    action: string;
    cancel: string;
  };
}

export interface TripIdentity {
  tripInstanceId: string;
  tripId: string;
  title: string;
  anchorDate: string;
  dateTile: DateTile;
  editHref: string;
  delete: TripDeleteAction | null;
}

export interface TripRow {
  trip: TripIdentity;
  bookedOffer: Offer | null;
  currentOffer: Offer | null;
  actions: {
    showBookingModal: boolean;
    canCreateBooking: boolean;
    showTrackers: boolean;
  };
}

export interface CollectionCard {
  groupId: string;
  label: string;
  createTripHref: string;
  recurringTrips: Array<{
    tripId: string;
    label: string;
    anchorWeekday: string;
    active: boolean;
    editHref: string;
  }>;
  upcomingTrips: Array<{
    tripId: string;
    tripInstanceId: string;
    label: string;
    title: string;
    lifecycle: TripLifecycle;
    attentionKind: TripAttentionKind | "";
  }>;
}

export interface DashboardPayload {
  today: string;
  filters: {
    selectedTripGroupIds: string[];
    includeBooked: boolean;
    groupOptions: Array<{
      value: string;
      label: string;
    }>;
  };
  counts: {
    totalUpcoming: number;
    totalBooked: number;
  };
  actionItems: DashboardActionItem[];
  collections: CollectionCard[];
  trips: TripRow[];
}

export interface TripOptionGroup {
  label: string;
  options: Array<{
    value: string;
    label: string;
  }>;
}

export interface DashboardUnmatchedBookingActionItem {
  kind: "unmatchedBooking";
  title: string;
  dateTile: DateTile;
  unmatchedBookingId: string;
  preferredTripInstanceId: string;
  offer: Offer;
  tripOptions: TripOptionGroup[];
  createTripHref: string;
}

export interface DashboardTripAttentionActionItem {
  kind: "tripAttention";
  attentionKind: TripAttentionKind;
  title: string;
  badge: string;
  row: TripRow;
}

export type DashboardActionItem =
  | DashboardUnmatchedBookingActionItem
  | DashboardTripAttentionActionItem;

export interface BookingPanelPayload {
  trip: TripIdentity;
  rows: Array<{
    bookingId: string;
    offer: Offer;
    warning: string;
  }>;
}

export interface BookingFormPayload {
  trip: TripIdentity;
  mode: "create" | "edit";
  form: {
    values: {
      bookingId: string;
      tripInstanceId: string;
      airline: string;
      originAirport: string;
      destinationAirport: string;
      departureDate: string;
      departureTime: string;
      arrivalTime: string;
      bookedPrice: string;
      recordLocator: string;
      notes: string;
    };
    submitLabel: string;
  };
  catalogs: {
    airports: Array<{ value: string; label: string; keywords: string }>;
    airlines: Array<{ value: string; label: string; keywords: string }>;
  };
}

export interface UnmatchedBookingFormPayload {
  dateTile: DateTile;
  offer: Offer;
  mode: "edit";
  form: {
    values: {
      bookingId: string;
      tripInstanceId: string;
      airline: string;
      originAirport: string;
      destinationAirport: string;
      departureDate: string;
      departureTime: string;
      arrivalTime: string;
      bookedPrice: string;
      recordLocator: string;
      notes: string;
    };
    submitLabel: string;
  };
  catalogs: {
    airports: Array<{ value: string; label: string; keywords: string }>;
    airlines: Array<{ value: string; label: string; keywords: string }>;
  };
}

export interface DashboardMutationPayload {
  dashboard: DashboardPayload;
}

export interface BookingMutationPayload extends DashboardMutationPayload {
  panel: BookingPanelPayload | null;
}

export interface TrackerPanelPayload {
  trip: TripIdentity;
  rows: Array<{
    rowId: string;
    travelDate: string;
    offer: Offer;
  }>;
  lastRefreshLabel: string;
  tripAnchorDate: string;
}

export interface FrontendBootstrap {
  dashboard?: {
    query: string;
    data: DashboardPayload;
  };
  bookingPanel?: {
    tripInstanceId: string;
    data: BookingPanelPayload;
  };
  bookingForm?: {
    tripInstanceId: string;
    mode: "create" | "edit";
    bookingId: string;
    data: BookingFormPayload;
  };
  trackerPanel?: {
    tripInstanceId: string;
    data: TrackerPanelPayload;
  };
  tripEditor?: {
    mode: "create" | "edit";
    tripId: string;
    query: string;
    data: TripEditorPayload;
  };
}

export interface TripEditorValues {
  tripId: string;
  label: string;
  tripKind: "one_time" | "weekly";
  tripGroupIds: string[];
  preferenceMode: "equal" | "ranked_bias";
  anchorDate: string;
  anchorWeekday: string;
  dataScope: string;
}

export interface TripEditorRouteOption {
  routeOptionId: string;
  savingsNeededVsPrevious: number;
  originAirports: string[];
  destinationAirports: string[];
  airlines: string[];
  dayOffset: number;
  startTime: string;
  endTime: string;
  fareClassPolicy: "include_basic" | "exclude_basic";
}

export interface TripEditorPayload {
  mode: "create" | "edit";
  values: TripEditorValues;
  routeOptions: TripEditorRouteOption[];
  sourceBooking: null | {
    unmatchedBookingId: string;
    referenceLabel: string;
    routeLabel: string;
    departureDate: string;
    departureTime: string;
    arrivalTime: string;
    airlineLabel: string;
  };
  recurringEditWarning: null | {
    linkedTripCount: number;
    linkedTripLabel: string;
    detachableTripInstanceId: string;
  };
  tripGroups: Array<{ value: string; label: string }>;
  catalogs: {
    airports: Array<{ value: string; label: string; keywords: string }>;
    airlines: Array<{ value: string; label: string; keywords: string }>;
    weekdays: string[];
    tripKinds: Array<{ value: string; label: string }>;
  };
}
