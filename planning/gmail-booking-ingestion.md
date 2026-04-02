# Gmail Booking Ingestion

`travel-agent` can now ingest booking confirmations directly from Gmail.

## Runtime Shape

- one-time auth:
  - `uv run python -m app.jobs.authorize_gmail_bookings`
- one-shot poller:
  - `uv run python -m app.jobs.poll_gmail_bookings --max-messages 10`
- optional macOS scheduler:
  - `uv run python -m app.jobs.install_launchd_booking_poller`

## Inputs

- checked-in config:
  - `config/gmail_integration.json`
- local secrets:
  - `config/local/gmail_oauth_client.json`
  - `config/local/gmail_oauth_token.json`
  - `config/local/openai_api_key.txt` or `OPENAI_API_KEY`

## Processing Pipeline

1. List recent Gmail messages from `INBOX`.
2. Skip messages already present in `booking_email_events`.
3. Apply a cheap keyword gate to ignore obvious spam/newsletter noise.
4. Send likely booking emails to the OpenAI extraction model.
5. Validate extracted legs and convert them to `BookingCandidate` rows.
6. Deduplicate against existing `Booking` and open `UnmatchedBooking` rows.
7. Use the existing booking matcher:
   - unique tracker match => `Booking`
   - ambiguous/no match => `UnmatchedBooking`
8. Append one `booking_email_events` audit row for the Gmail message.

## Statuses

`booking_email_events.processing_status` is one of:

- `ignored`
- `resolved_auto`
- `needs_resolution`
- `duplicate`
- `error`

## Current Scope

Supported now:

- booking confirmation emails
- multi-leg extraction
- automatic booking creation when a leg matches confidently
- fallback to `Resolve` when matching is ambiguous

Intentionally deferred:

- automatic cancellation handling
- automatic itinerary-change reconciliation
- attachment or PDF parsing
- Gmail label workflows
