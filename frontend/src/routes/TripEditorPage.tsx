import { useMutation, useQuery } from "@tanstack/react-query";
import { startTransition, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "../lib/api";
import { tripEditorQueryKey } from "../lib/queryKeys";
import type { TripEditorPayload, TripEditorRouteOption, TripEditorValues } from "../types";
import { MultiSelectField } from "../components/MultiSelectField";
import { SearchSelectField } from "../components/SearchSelectField";
import { TimeRangeField } from "../components/TimeRangeField";

function blankRouteOption(): TripEditorRouteOption {
  return {
    routeOptionId: "",
    savingsNeededVsPrevious: 0,
    originAirports: [],
    destinationAirports: [],
    airlines: [],
    dayOffset: 0,
    startTime: "00:00",
    endTime: "23:59",
    fareClass: "basic_economy",
  };
}

const TRAVEL_DAY_OPTIONS = [
  { value: "-1", label: "Day before" },
  { value: "0", label: "Same day" },
  { value: "1", label: "Day after" },
];

function fallbackCancelUrl(values: TripEditorValues, searchParams: URLSearchParams) {
  const explicitGroupId = searchParams.get("trip_group_id");
  if (explicitGroupId) {
    return `/#group-${explicitGroupId}`;
  }
  if (values.tripKind === "weekly" && values.tripGroupIds.length === 1) {
    return `/#group-${values.tripGroupIds[0]}`;
  }
  return "/#all-travel";
}

export function TripEditorPage() {
  const navigate = useNavigate();
  const { tripId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const mode = tripId ? "edit" : "create";
  const [values, setValues] = useState<TripEditorValues | null>(null);
  const [routeOptions, setRouteOptions] = useState<TripEditorRouteOption[]>([blankRouteOption()]);
  const [error, setError] = useState("");
  const [savePhase, setSavePhase] = useState<"idle" | "saving" | "redirecting">("idle");

  const editorParams = useMemo(() => {
    const params = new URLSearchParams();
    const tripKind = searchParams.get("trip_kind");
    const tripGroupId = searchParams.get("trip_group_id");
    const unmatchedBookingId = searchParams.get("unmatched_booking_id");
    const tripLabel = searchParams.get("trip_label");
    const tripInstanceId = searchParams.get("trip_instance_id");
    if (tripKind) {
      params.set("trip_kind", tripKind);
    }
    if (tripGroupId) {
      params.set("trip_group_id", tripGroupId);
    }
    if (unmatchedBookingId) {
      params.set("unmatched_booking_id", unmatchedBookingId);
    }
    if (tripLabel) {
      params.set("trip_label", tripLabel);
    }
    if (tripInstanceId) {
      params.set("trip_instance_id", tripInstanceId);
    }
    return params;
  }, [searchParams]);

  const formQuery = useQuery({
    queryKey: tripEditorQueryKey(mode, tripId, editorParams.toString()),
    queryFn: () => (tripId ? api.tripEditorEdit(tripId, editorParams) : api.tripEditorNew(editorParams)),
  });

  const cancelHref = useMemo(
    () => (formQuery.data ? fallbackCancelUrl(formQuery.data.values, searchParams) : "/#all-travel"),
    [formQuery.data, searchParams],
  );

  useEffect(() => {
    if (!formQuery.data) {
      return;
    }
    setValues(formQuery.data.values);
    setRouteOptions(formQuery.data.routeOptions.length ? formQuery.data.routeOptions : [blankRouteOption()]);
    setError("");
    setSavePhase("idle");
  }, [formQuery.data]);

  useEffect(() => {
    if (!values || routeOptions.length > 1 || values.preferenceMode === "equal") {
      return;
    }
    setValues((current) => (current ? { ...current, preferenceMode: "equal" } : current));
  }, [routeOptions.length, values]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!values) {
        throw new Error("Trip form is not ready.");
      }
      if (mode === "edit") {
        return api.updateTrip(
          tripId,
          values,
          routeOptions,
          formQuery.data?.sourceBooking?.unmatchedBookingId ?? "",
        );
      }
      return api.createTrip(
        values,
        routeOptions,
        formQuery.data?.sourceBooking?.unmatchedBookingId ?? "",
      );
    },
    onSuccess: (result) => {
      setSavePhase("redirecting");
      startTransition(() => {
        navigate(result.redirectTo, {
          state: { toast: { message: result.message, kind: "success" as const } },
        });
      });
    },
    onError: (err) => {
      setSavePhase("idle");
      setError(err instanceof Error ? err.message : "Unable to save trip.");
    },
  });

  const detachMutation = useMutation({
    mutationFn: (tripInstanceId: string) => api.detachTripInstance(tripInstanceId),
    onSuccess: (result) => {
      setSavePhase("redirecting");
      navigate(result.redirectTo, {
        state: { toast: { message: result.message, kind: "success" as const } },
      });
    },
    onError: (err) => {
      setSavePhase("idle");
      setError(err instanceof Error ? err.message : "Unable to detach trip.");
    },
  });

  function updateValues(patch: Partial<TripEditorValues>) {
    setValues((current) => (current ? { ...current, ...patch } : current));
  }

  function updateRoute(index: number, patch: Partial<TripEditorRouteOption>) {
    setRouteOptions((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function removeRoute(index: number) {
    setRouteOptions((current) => (current.length === 1 ? current : current.filter((_, itemIndex) => itemIndex !== index)));
  }

  function moveRoute(index: number, direction: -1 | 1) {
    setRouteOptions((current) => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) {
        return current;
      }
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  if (formQuery.isError) {
    return (
      <div className="app-shell">
        <div className="surface">
          <p className="inline-error">{formQuery.error instanceof Error ? formQuery.error.message : "Unable to load trip editor."}</p>
        </div>
      </div>
    );
  }
  if (formQuery.isLoading || !values || !formQuery.data) {
    return <div className="app-shell"><div className="surface-loading">Loading trip editor…</div></div>;
  }

  const payload = formQuery.data;
  const isEdit = mode === "edit";
  const weekly = values.tripKind === "weekly";
  const weekdays = payload.catalogs.weekdays;
  const idleSubmitLabel = isEdit ? "Save trip" : "Create trip";
  const collectionsHelper = weekly
    ? (!values.tripGroupIds.length ? "Leave blank to create a matching collection." : "")
    : (!payload.tripGroups.length ? "No collections yet." : "");

  return (
    <div className="app-shell app-shell--editor">
      <section className="surface editor-surface">
        <header className="editor-header">
          <div>
            <p className="page-header__eyebrow">Trip</p>
            <h1>{isEdit ? values.label : "Create trip"}</h1>
          </div>
        </header>

        {payload.sourceBooking ? (
          <section className="info-card-react">
            <strong>Starting from {payload.sourceBooking.referenceLabel}.</strong>
            <p>
              {payload.sourceBooking.routeLabel} · {payload.sourceBooking.departureDate} · {payload.sourceBooking.departureTime}
              {payload.sourceBooking.arrivalTime ? `–${payload.sourceBooking.arrivalTime}` : ""} · {payload.sourceBooking.airlineLabel}
            </p>
            <p className="muted-copy">Saving links this booking.</p>
          </section>
        ) : null}

        {payload.recurringEditWarning ? (
          <section className="warning-card-react">
            <strong>
              Editing this recurring trip will affect {payload.recurringEditWarning.linkedTripCount} {payload.recurringEditWarning.linkedTripLabel}.
            </strong>
            <p>If you only want to edit one specific trip instance, detach that trip first and then edit it separately.</p>
            {payload.recurringEditWarning.detachableTripInstanceId ? (
              <div className="warning-card-react__actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => detachMutation.mutate(payload.recurringEditWarning!.detachableTripInstanceId)}
                >
                  Detach this trip instead
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        {error ? <p className="inline-error">{error}</p> : null}

        <form
          className="trip-editor-form"
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            setSavePhase("saving");
            saveMutation.mutate();
          }}
        >
          <div className="trip-editor-grid trip-editor-grid--overview">
            <label className="field-block--span-2">
              <span>Trip label</span>
              <input
                type="text"
                value={values.label}
                onChange={(event) => updateValues({ label: event.target.value })}
                disabled={saveMutation.isPending}
              />
            </label>

            <div className="field-block">
              <span>Trip type</span>
              {isEdit ? (
                <>
                  <div className="trip-type-lock">
                    <span className={`trip-type-lock__pill ${values.tripKind === "one_time" ? "is-selected" : ""}`}>One-time</span>
                    <span className={`trip-type-lock__pill ${values.tripKind === "weekly" ? "is-selected" : ""}`}>Weekly</span>
                  </div>
                  <small className="muted-copy">Trip type is fixed after creation.</small>
                </>
              ) : (
                <div className="trip-type-switch">
                  {payload.catalogs.tripKinds.map((kind) => (
                    <label key={kind.value} className={`trip-type-switch__pill ${values.tripKind === kind.value ? "is-selected" : ""}`}>
                      <input
                        type="radio"
                        name="tripKind"
                        value={kind.value}
                        checked={values.tripKind === kind.value}
                        onChange={() => updateValues({ tripKind: kind.value as "one_time" | "weekly" })}
                      />
                      <span>{kind.label}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="field-block field-block--span-2">
              <span>{weekly ? "Target collections" : "Collections"}</span>
              <MultiSelectField
                options={payload.tripGroups}
                values={values.tripGroupIds}
                onChange={(tripGroupIds) => updateValues({ tripGroupIds })}
                placeholder="Search collections"
                emptyText={weekly ? "Will create matching collection" : "No collections"}
              />
              {collectionsHelper ? <small className="muted-copy">{collectionsHelper}</small> : null}
            </div>

            {weekly ? (
              <div className="field-block field-block--full">
                <span>Repeat on</span>
                <div className="weekday-switch">
                  {weekdays.map((weekday) => (
                    <label key={weekday} className={`weekday-switch__pill ${values.anchorWeekday === weekday ? "is-selected" : ""}`}>
                      <input
                        type="radio"
                        name="anchorWeekday"
                        checked={values.anchorWeekday === weekday}
                        onChange={() => updateValues({ anchorWeekday: weekday })}
                      />
                      <span>{weekday.slice(0, 3)}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <label>
                <span>Travel date</span>
                <input
                  type="date"
                  value={values.anchorDate}
                  onChange={(event) => updateValues({ anchorDate: event.target.value })}
                  disabled={saveMutation.isPending}
                />
              </label>
            )}
          </div>

          <section className="choice-card-surface">
            <div className="section-header-react section-header-react--editor">
              <div className="section-header-react__copy">
                <h2>Flight options</h2>
              </div>
              <div className="section-header-react__controls">
                {routeOptions.length > 1 ? (
                  <div className="trip-type-switch route-preference-bar__switch">
                    <label className={`trip-type-switch__pill ${values.preferenceMode === "equal" ? "is-selected" : ""}`}>
                      <input
                        type="radio"
                        name="preferenceMode"
                        checked={values.preferenceMode === "equal"}
                        onChange={() => updateValues({ preferenceMode: "equal" })}
                      />
                      <span>Equal</span>
                    </label>
                    <label className={`trip-type-switch__pill ${values.preferenceMode === "ranked_bias" ? "is-selected" : ""}`}>
                      <input
                        type="radio"
                        name="preferenceMode"
                        checked={values.preferenceMode === "ranked_bias"}
                        onChange={() => updateValues({ preferenceMode: "ranked_bias" })}
                      />
                      <span>Ordered</span>
                    </label>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setRouteOptions((current) => [...current, blankRouteOption()])}
                >
                  Add route
                </button>
              </div>
            </div>
            {routeOptions.length > 1 && values.preferenceMode === "ranked_bias" ? (
              <div className="route-preference-note muted-copy">
                Option 1 is preferred. Lower options only win when they beat the option above by the amount you set.
              </div>
            ) : null}
            <div className="route-editor-stack">
              {routeOptions.map((route, index) => (
                <article key={`${route.routeOptionId || "new"}-${index}`} className="route-card-react">
                  <div className="route-card-react__header">
                    <div className="route-card-react__title">
                      <strong>Option {index + 1}</strong>
                      {routeOptions.length > 1 && values.preferenceMode === "ranked_bias" && index === 0 ? (
                        <small className="muted-copy">Preferred option</small>
                      ) : null}
                    </div>
                    <div className="route-card-react__actions">
                      <button type="button" className="ghost-button" onClick={() => moveRoute(index, -1)} disabled={index === 0}>Up</button>
                      <button type="button" className="ghost-button" onClick={() => moveRoute(index, 1)} disabled={index === routeOptions.length - 1}>Down</button>
                      <button type="button" className="danger-button" onClick={() => removeRoute(index)} disabled={routeOptions.length === 1}>Remove</button>
                    </div>
                  </div>
                  <div className="trip-editor-grid route-card-react__grid">
                    <div className="field-block">
                      <span>Origin airports</span>
                      <MultiSelectField
                        options={payload.catalogs.airports}
                        values={route.originAirports}
                        onChange={(originAirports) => updateRoute(index, { originAirports })}
                        placeholder="Search origins"
                        maxSelections={3}
                      />
                    </div>
                    <div className="field-block">
                      <span>Destination airports</span>
                      <MultiSelectField
                        options={payload.catalogs.airports}
                        values={route.destinationAirports}
                        onChange={(destinationAirports) => updateRoute(index, { destinationAirports })}
                        placeholder="Search destinations"
                        maxSelections={3}
                      />
                    </div>
                    <div className="field-block">
                      <span>Airlines</span>
                      <MultiSelectField
                        options={payload.catalogs.airlines}
                        values={route.airlines}
                        onChange={(airlines) => updateRoute(index, { airlines })}
                        placeholder="Search airlines"
                      />
                    </div>
                    <div className="field-block">
                      <span>Travel day</span>
                      <SearchSelectField
                        options={TRAVEL_DAY_OPTIONS.map((item) => ({
                          value: item.value,
                          label: item.label,
                          keywords: item.label,
                          summary: item.label,
                        }))}
                        value={String(route.dayOffset)}
                        onChange={(dayOffset) => updateRoute(index, { dayOffset: Number(dayOffset) })}
                        placeholder="Choose day"
                        disabled={saveMutation.isPending}
                      />
                    </div>
                    <div className="field-block">
                      <span>Fare</span>
                      <SearchSelectField
                        options={payload.catalogs.fareClasses.map((item) => ({
                          value: item.value,
                          label: item.label,
                          keywords: item.keywords,
                          summary: item.label,
                        }))}
                        value={route.fareClass}
                        onChange={(fareClass) => updateRoute(index, { fareClass: fareClass as "basic_economy" | "economy" })}
                        placeholder="Choose fare"
                        disabled={saveMutation.isPending}
                      />
                    </div>
                    <TimeRangeField
                      label="Departure window"
                      startTime={route.startTime}
                      endTime={route.endTime}
                      onChange={(next) => updateRoute(index, next)}
                      disabled={saveMutation.isPending}
                    />
                    {values.preferenceMode === "ranked_bias" && index > 0 ? (
                      <label className="field-block field-block--full">
                        <span>Savings to beat option {index}</span>
                        <input
                          type="number"
                          min={0}
                          step={1}
                          value={route.savingsNeededVsPrevious}
                          onChange={(event) => updateRoute(index, { savingsNeededVsPrevious: Math.max(0, Number(event.target.value || 0)) })}
                          disabled={saveMutation.isPending}
                        />
                      </label>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <div className="editor-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate(cancelHref)}
              disabled={saveMutation.isPending || savePhase === "redirecting"}
            >
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={saveMutation.isPending || savePhase === "redirecting"}>
              {savePhase === "saving" ? "Saving…" : savePhase === "redirecting" ? "Opening…" : idleSubmitLabel}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
