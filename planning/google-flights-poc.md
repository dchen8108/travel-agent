# Google Flights POC Findings

## Objective

Reduce the remaining unknowns around the free-only v0 before implementation starts.

## What Is Proven So Far

### 1. No API key is required for basic Google Flights web access

A direct request to a query-style Google Flights URL returns `HTTP/2 200` without any API key:

```text
https://www.google.com/travel/flights?q=Flights%20from%20BUR%20to%20SFO%20on%202026-05-12%20through%202026-05-14
```

This is enough to support the idea of:

- generated search links
- opening Google Flights from the local app
- manual tracker setup by the user

Important caveat:

- this proves link reachability, not a stable public URL contract from Google
- generated links should therefore be treated as best-effort
- manual tracker-link paste must remain supported

### 2. The tracked-flights surface is a web page, not a public API

A direct request to:

```text
https://www.google.com/travel/flights/saves
```

also returns `HTTP/2 200`, which supports the assumption that this is an account-backed web surface rather than a separate public API product.

### 3. There is no provider-specific API credential for the Google Flights plan

The free-only design does not rely on any published Google Flights API key or secret.

The critical dependency is access to:

- Google Flights tracking emails
- and optionally the Gmail inbox that receives them

### 4. A real Google Flights alert email is parseable enough to support the product

The sample email at:

`/Users/davidchen/Downloads/Prices for your tracked flights to Burbank, New York, Los Angeles have changed.eml`

proves that the plain-text body includes:

- human-readable route names, for example `San Francisco to Burbank`
- travel date, for example `Thu, Jun 4`
- trip type and cabin line, for example `One way · Economy (include Basic) · 1 adult`
- specific tracked flight observations with:
  - departure and arrival times
  - airline
  - stop pattern
  - airport code pair, for example `SFO–BUR`
  - current price
  - prior price and direction, for example `dropped from $149`
- Google Flights links for each market and each flight option

This is enough to support:

- segment-level tracker matching
- current-price observation storage
- price-direction tracking
- booked-vs-current comparison logic

## What Is Still Unknown

### 1. Email parse quality

The first sample is strong, but we still need at least one more sample to know:

- how stable the format is across multiple alerts
- whether round-trip commute use cases can be represented cleanly through separate segment alerts
- whether airline and flexibility context remains present often enough

### 2. Generated-link quality

We have only proven that a query-style Google Flights URL is reachable.

We have not proven:

- that the generated link always lands on the exact intended trip search
- that it will always be the best UX for enabling tracking

That is why manual link paste remains in the hardened spec.

### 3. Gmail auth path

Automatic inbox polling is still dependent on the actual Google account type and chosen auth method.

The baseline product no longer depends on this, because manual `.eml` upload is sufficient for the first working version.

## Current Confidence

### High confidence

- local web app
- local CSV and JSON storage
- Google Flights link-out flow
- tracker-management UX
- segment-level observation parsing from the plain-text body
- manual booking capture
- manual `.eml` upload and parsed observation storage

### Medium confidence

- automatic Gmail IMAP ingestion
- fully reliable generated Google Flights links
- fully reliable booked-trip recommendation quality from Google email content alone

## What We Need From The User

To close the biggest remaining unknowns, the user can provide:

1. one or more real Google Flights tracking emails
2. ideally the raw `.eml` export of those emails
3. if automatic Gmail sync is desired, the Gmail account details and preferred auth method

There is no Google Flights API key to provide for this design.

## Recommended Implementation Stance

Proceed only with the hardened baseline:

- generated links plus manual link paste
- segment-level trackers for outbound and return legs
- manual `.eml` upload first
- Gmail IMAP later if the user wants it

That is the version with the best chance of being working end to end today.
