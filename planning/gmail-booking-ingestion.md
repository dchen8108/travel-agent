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

1. On first run, backfill every current message in `INBOX`. After that, use Gmail history sync to fetch only newly added messages.
2. If `allowed_from_addresses` is configured, ignore messages whose sender is not allowlisted before extraction.
3. Skip messages already present in `booking_email_events`, except retryable prior `error` rows below the retry cap.
4. Apply a cheap keyword gate to ignore obvious spam/newsletter noise.
5. Send likely booking emails to the OpenAI extraction model.
6. If the email is a cancellation, try to match it to existing `Booking` rows and mark them `cancelled`.
7. Otherwise validate extracted legs and convert them into booking candidates.
8. Deduplicate against existing `Booking` rows.
9. Use the existing booking matcher:
   - unique trip-instance match => linked `Booking`
   - ambiguous/no match => unlinked `Booking`
10. Append one `booking_email_events` audit row for the Gmail message.

The Gmail poller uses two checkpoints:

- Gmail `historyId` state in `config/local/gmail_sync_state.json`
- a per-message ledger in `booking_email_events`

That combination prevents already-processed emails from going back through the LLM while still allowing bounded retries for transient failures.

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
- cancellation emails that can be matched to an existing booking
- multi-leg extraction
- automatic booking creation when a leg matches confidently
- fallback to unlinked booking review inline on the dashboard when matching is ambiguous
- default log redaction for model inputs/outputs, with opt-in full model I/O logging through `debug_log_model_io`

## Config Layering

`config/gmail_integration.json` currently carries both:

- runtime poller behavior such as `max_messages_per_poll`, `allowed_from_addresses`, retry caps, and model choice
- launchd installer defaults such as `launchd_poll_interval_seconds` and `launchd_max_messages`

That split is intentional. The installer decides how often launchd starts the job, while the worker still enforces its own runtime cap when the job executes.

Intentionally deferred:

- automatic itinerary-change reconciliation
- attachment or PDF parsing
- Gmail label workflows
