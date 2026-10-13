import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";

import { api } from "../lib/api";
import { v2WorkspaceQueryKey } from "../lib/queryKeys";
import type { CollectionCard, V2TripItem, V2TripState, V2WorkspacePayload } from "../types";
import { V2AttentionCard } from "./V2AttentionCard";
import { V2TripCard } from "./V2TripCard";
import "./v2.css";

type ViewKey = "home" | "schedule" | "inbox" | "rules";
type ScheduleFilter = "all" | V2TripState;

const NAV_ITEMS: Array<{ key: ViewKey; label: string; href: string }> = [
  { key: "home", label: "Home", href: "/v2" },
  { key: "schedule", label: "Schedule", href: "/v2/schedule" },
  { key: "inbox", label: "Inbox", href: "/v2/inbox" },
  { key: "rules", label: "Rules", href: "/v2/rules" },
];

function viewFromPath(pathname: string): ViewKey {
  if (pathname.startsWith("/v2/schedule")) return "schedule";
  if (pathname.startsWith("/v2/inbox")) return "inbox";
  if (pathname.startsWith("/v2/rules")) return "rules";
  return "home";
}

function V2Glyph({ name }: { name: ViewKey }) {
  if (name === "schedule") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4.5h14A1.5 1.5 0 0 1 20.5 6v13A1.5 1.5 0 0 1 19 20.5H5A1.5 1.5 0 0 1 3.5 19V6A1.5 1.5 0 0 1 5 4.5ZM7 2.5v4M17 2.5v4M3.5 9h17M7 13h3M14 13h3M7 17h3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>;
  }
  if (name === "inbox") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5h16v13H4v-13Zm0 8h4l1.5 2h5l1.5-2h4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg>;
  }
  if (name === "rules") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h7M15 7h5M4 17h4M12 17h8M11 4v6M8 14v6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /><circle cx="13" cy="7" r="2" fill="none" stroke="currentColor" strokeWidth="1.8" /><circle cx="10" cy="17" r="2" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>;
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>;
}

function V2Navigation({ mobile = false }: { mobile?: boolean }) {
  return (
    <nav className={mobile ? "v2-mobile-nav" : "v2-nav"} aria-label="V2 navigation">
      {NAV_ITEMS.map((item) => (
        <NavLink key={item.key} to={item.href} end={item.key === "home"}>
          <V2Glyph name={item.key} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function PageHeading({ eyebrow, title, copy, actions }: { eyebrow: string; title: string; copy: string; actions?: ReactNode }) {
  return (
    <header className="v2-page-heading">
      <div>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
        <span>{copy}</span>
      </div>
      {actions ? <div className="v2-page-heading__actions">{actions}</div> : null}
    </header>
  );
}

function StatCard({ number, label, detail, tone = "neutral" }: { number: number; label: string; detail: string; tone?: "neutral" | "attention" | "good" }) {
  return (
    <article className={`v2-stat v2-stat--${tone}`}>
      <span className="v2-stat__number">{String(number).padStart(2, "0")}</span>
      <div><strong>{label}</strong><span>{detail}</span></div>
    </article>
  );
}

function HomeView({ data }: { data: V2WorkspacePayload }) {
  const activeTrips = data.trips.filter((item) => item.state !== "skipped");
  const nextTrips = activeTrips.slice(0, 4);
  const nextTrip = nextTrips[0];
  const formattedToday = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date(`${data.today}T12:00:00`));

  return (
    <>
      <section className="v2-hero">
        <div className="v2-hero__copy">
          <p>Flight desk · {formattedToday}</p>
          <h1>{data.stats.attentionCount ? "Your next move is clear." : "Everything is on course."}</h1>
          <span>
            {data.stats.attentionCount
              ? `${data.stats.attentionCount} ${data.stats.attentionCount === 1 ? "decision needs" : "decisions need"} your attention.`
              : "No booking decisions need you right now."}
          </span>
        </div>
        <div className="v2-hero__route" aria-hidden="true">
          <span>LAX</span><i /><span>SFO</span>
        </div>
        {nextTrip ? (
          <div className="v2-hero__next">
            <span>Next departure</span>
            <strong>{nextTrip.row.trip.title}</strong>
            <small>{nextTrip.row.trip.dateTile.weekday} · {nextTrip.row.trip.dateTile.monthDay}</small>
          </div>
        ) : null}
      </section>

      <section className="v2-stats" aria-label="Travel summary">
        <StatCard number={data.stats.attentionCount} label="Attention" detail="open decisions" tone={data.stats.attentionCount ? "attention" : "good"} />
        <StatCard number={data.stats.departuresNext14Days} label="Departures" detail="next 14 days" />
        <StatCard number={data.stats.bookedNext14Days} label="Booked" detail="next 14 days" tone="good" />
        <StatCard number={data.stats.trackedTrips} label="Tracking" detail="live trip dates" />
      </section>

      <div className="v2-home-grid">
        <section className="v2-panel v2-panel--departures">
          <header className="v2-panel__heading">
            <div><span>Itinerary</span><h2>Next departures</h2></div>
            <NavLink to="/v2/schedule">Full schedule</NavLink>
          </header>
          <div className="v2-trip-list">
            {nextTrips.length ? nextTrips.map((item) => (
              <V2TripCard key={item.row.trip.tripInstanceId} item={item} />
            )) : <div className="v2-empty"><strong>Clear runway.</strong><span>No upcoming departures.</span></div>}
          </div>
        </section>

        <section className="v2-panel v2-panel--decisions">
          <header className="v2-panel__heading">
            <div><span>Signal</span><h2>Decision queue</h2></div>
            {data.attentionItems.length ? <NavLink to="/v2/inbox">View all</NavLink> : null}
          </header>
          <div className="v2-attention-list">
            {data.attentionItems.length ? data.attentionItems.slice(0, 3).map((item, index) => (
              <V2AttentionCard key={item.kind === "unmatchedBooking" ? item.unmatchedBookingId : `${item.row.trip.tripInstanceId}-${index}`} item={item} today={data.today} />
            )) : (
              <div className="v2-clear-state">
                <span className="v2-clear-state__mark">✓</span>
                <strong>No decisions waiting</strong>
                <p>Milemark is still watching every active route in the background.</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function monthLabel(anchorDate: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" })
    .format(new Date(`${anchorDate}T12:00:00`));
}

function ScheduleView({ data }: { data: V2WorkspacePayload }) {
  const [filter, setFilter] = useState<ScheduleFilter>("all");
  const [visibleMonthCount, setVisibleMonthCount] = useState(2);
  const groups = useMemo(() => {
    const filtered = filter === "all" ? data.trips : data.trips.filter((item) => item.state === filter);
    const grouped = new Map<string, V2TripItem[]>();
    filtered.forEach((item) => {
      const label = monthLabel(item.row.trip.anchorDate);
      grouped.set(label, [...(grouped.get(label) ?? []), item]);
    });
    return [...grouped.entries()];
  }, [data.trips, filter]);

  return (
    <>
      <PageHeading
        eyebrow="Travel timeline"
        title="Upcoming schedule"
        copy={`${data.horizonWeeks} weeks of travel intent, organized by departure date.`}
        actions={<a className="v2-button v2-button--primary" href="/trips/new">New trip</a>}
      />
      <div className="v2-filter-bar" role="group" aria-label="Filter schedule">
        {(["all", "planning", "booked", "skipped"] as ScheduleFilter[]).map((value) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "is-active" : ""}
            onClick={() => {
              setFilter(value);
              setVisibleMonthCount(2);
            }}
          >
            {value === "all" ? "All trips" : value === "planning" ? "Planning" : value[0].toUpperCase() + value.slice(1)}
            <span>{value === "all" ? data.trips.length : data.trips.filter((item) => item.state === value).length}</span>
          </button>
        ))}
      </div>
      <div className="v2-months">
        {groups.slice(0, visibleMonthCount).map(([label, trips]) => (
          <section key={label} className="v2-month">
            <header><h2>{label}</h2><span>{trips.length} {trips.length === 1 ? "departure" : "departures"}</span></header>
            <div className="v2-trip-list">
              {trips.map((item) => <V2TripCard key={item.row.trip.tripInstanceId} item={item} />)}
            </div>
          </section>
        ))}
        {groups.length > visibleMonthCount ? (
          <button
            className="v2-months__more"
            type="button"
            onClick={() => setVisibleMonthCount((current) => current + 2)}
          >
            Show later months
            <span>{groups.length - visibleMonthCount} remaining</span>
          </button>
        ) : null}
        {!groups.length ? <div className="v2-empty"><strong>No matching trips.</strong><span>Choose another schedule filter.</span></div> : null}
      </div>
    </>
  );
}

function InboxView({ data }: { data: V2WorkspacePayload }) {
  return (
    <>
      <PageHeading
        eyebrow="Decision inbox"
        title="Only the work that needs you"
        copy="Booking gaps, better fares, overbooked dates, and imports that need a destination."
      />
      <section className="v2-inbox-summary">
        <strong>{String(data.attentionItems.length).padStart(2, "0")}</strong>
        <span>open {data.attentionItems.length === 1 ? "decision" : "decisions"}</span>
        <i />
        <p>Everything else continues automatically.</p>
      </section>
      <div className="v2-inbox-list">
        {data.attentionItems.length ? data.attentionItems.map((item, index) => (
          <V2AttentionCard key={item.kind === "unmatchedBooking" ? item.unmatchedBookingId : `${item.row.trip.tripInstanceId}-${index}`} item={item} today={data.today} />
        )) : (
          <div className="v2-clear-state v2-clear-state--large">
            <span className="v2-clear-state__mark">✓</span>
            <strong>Inbox zero</strong>
            <p>Your bookings and tracked routes agree. There is nothing to resolve.</p>
          </div>
        )}
      </div>
    </>
  );
}

function RuleCollection({ collection }: { collection: CollectionCard }) {
  return (
    <article className="v2-rule-card">
      <header>
        <div><span>Collection</span><h2>{collection.label}</h2></div>
        <a href={collection.createTripHref}>Add trip</a>
      </header>
      <div className="v2-rule-card__rules">
        {collection.recurringTrips.map((trip) => (
          <a key={trip.tripId} className="v2-rule" href={trip.editHref}>
            <span className={`v2-rule__status${trip.active ? " is-active" : ""}`} />
            <span><strong>{trip.label}</strong><small>Every {trip.anchorWeekday}</small></span>
            <b>{trip.active ? "Active" : "Paused"}</b>
          </a>
        ))}
        {!collection.recurringTrips.length ? <div className="v2-empty v2-empty--small"><span>No recurring rules.</span></div> : null}
      </div>
      {collection.upcomingTrips.length ? (
        <div className="v2-rule-card__dates">
          <span>Next dates</span>
          <div>{collection.upcomingTrips.slice(0, 10).map((trip) => (
            <a key={trip.tripInstanceId} className={`v2-date-chip v2-date-chip--${trip.lifecycle}`} href={`/trips/${trip.tripId}/edit?trip_instance_id=${trip.tripInstanceId}`}>
              {trip.title}
            </a>
          ))}</div>
        </div>
      ) : null}
    </article>
  );
}

function RulesView({ data }: { data: V2WorkspacePayload }) {
  const ruleCount = data.collections.reduce((total, collection) => total + collection.recurringTrips.length, 0);
  return (
    <>
      <PageHeading
        eyebrow="Automation"
        title="Recurring travel rules"
        copy={`${ruleCount} ${ruleCount === 1 ? "rule keeps" : "rules keep"} your future schedule and fare searches generated.`}
        actions={<a className="v2-button v2-button--primary" href="/trips/new?trip_kind=weekly">New rule</a>}
      />
      <div className="v2-rules-grid">
        {data.collections.map((collection) => <RuleCollection key={collection.groupId} collection={collection} />)}
        {!data.collections.length ? <div className="v2-empty"><strong>No collections yet.</strong><span>Create a recurring travel rule to begin.</span></div> : null}
      </div>
    </>
  );
}

export function V2Page() {
  const location = useLocation();
  const view = viewFromPath(location.pathname);
  const query = useQuery({
    queryKey: v2WorkspaceQueryKey(),
    queryFn: api.v2Workspace,
  });

  useEffect(() => {
    document.body.classList.add("v2-route");
    document.title = "Milemark · Flight desk";
    return () => {
      document.body.classList.remove("v2-route");
      document.title = "Milemark";
    };
  }, []);

  return (
    <div className="v2-app">
      <aside className="v2-rail">
        <a className="v2-brand" href="/v2"><span>MM</span><strong>Milemark</strong><small>Flight operations</small></a>
        <V2Navigation />
        <div className="v2-rail__footer">
          <span>Version two</span>
          <a href="/">Open classic</a>
        </div>
      </aside>
      <header className="v2-mobile-header">
        <a className="v2-brand" href="/v2"><span>MM</span><strong>Milemark</strong></a>
        <a href="/">Classic</a>
      </header>
      <V2Navigation mobile />
      <main className="v2-main">
        {query.isPending ? <div className="v2-loading"><i /><span>Preparing your flight desk…</span></div> : null}
        {query.isError ? (
          <div className="v2-error"><strong>Flight desk unavailable</strong><span>{query.error instanceof Error ? query.error.message : "Unable to load v2."}</span><button type="button" onClick={() => void query.refetch()}>Try again</button></div>
        ) : null}
        {query.data && view === "home" ? <HomeView data={query.data} /> : null}
        {query.data && view === "schedule" ? <ScheduleView data={query.data} /> : null}
        {query.data && view === "inbox" ? <InboxView data={query.data} /> : null}
        {query.data && view === "rules" ? <RulesView data={query.data} /> : null}
      </main>
    </div>
  );
}
