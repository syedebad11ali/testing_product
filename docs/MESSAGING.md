# Buyer-seller messaging (v1, text only)

Private conversations between a signed-in buyer and the seller of a listing. Separate from the AI assistant: message text is
never sent to an AI provider, never put in cookies or URLs, and never written to ordinary logs (a test greps the code for AI/network imports).

## Model (migration `0006_moderation_messaging.sql`)
`listings` (id, ref, seller_id, title, area, status) · `conversations` (UNIQUE listing+buyer, per-side `*_read_ts`) · `messages`
(`ts` in microseconds, strictly increasing per conversation; UNIQUE `client_id` per sender makes retries idempotent) ·
`user_blocks` · `message_reports`. Indexes cover participant lookup, listing lookup and chronological pagination.

**Listings:** the site's demo properties (`p1`..`p8`) are static data with no seller account, so messaging has its own `listings` table.
Users create listings with `POST /listings` (server-generated `ref`, so nobody can claim a demo ref). For local demos run
`DEMO_SELLER_PASSWORD='<12+ chars>' python scripts/seed_demo_listings.py` (refuses to run in production).
Until a listing row exists for a property, "Chat with seller" says messaging is not available for it.

## Endpoints (all under `/api/v1`, `no-store`, CSRF on writes, rate limited by user and IP: `MESSAGE_RATE_LIMIT_PER_MIN`)
| Method / path | Notes |
|---|---|
| `GET /listings/by-ref/<ref>` | Public. `{id, ref, title, area, contactable, own}`; never the seller. |
| `POST /listings` | Login. `{title, area}` -> 201. |
| `POST /messages/conversations` | Login. `{listing_id}`; create-or-open (idempotent). Errors: `own_listing`, `listing_unavailable`, `blocked`. |
| `GET /messages/conversations?page=` | Inbox: counterpart (first name + initial), listing title, preview, unread, `counterpart_available`. |
| `GET /messages/conversations/<id>?limit=&before=&after=` | Oldest-first page. `before` = older history, `after` = polling. Does not mark read. |
| `POST /messages/conversations/<id>/messages` | `{body, client_id?}`; 1-2000 chars, control chars stripped. Sender = session user. |
| `POST .../read`, `.../report`, `.../block`, `.../unblock` | Participants only. Report: `{reason, message_id?}`; `message_id` must be a message of that same conversation (else `400 invalid_message`). The report dialog lets the reporter pick the whole conversation or one of the other person's 20 most recent messages (plain-text previews). |
| `GET /messages/unread-count` | Total unread. |
| Admin: `GET /admin/reports`, `GET /admin/reports/<id>/thread`, `POST /admin/reports/<id>/resolve` | See below. |

## Rules
* Membership is checked on every call. A non-participant gets the same `404 not_found` (same text) as for a missing id.
* Rendering: message text is written with `textContent`; HTML stays inert (browser test sends an `<img onerror>` payload).
* Updates are **polling every 6 s while the tab is visible**, not real-time push.
* Bans: a banned user's session dies at once (central session lookup), so they cannot open, read or send. The counterpart gets
  `409 conversation_closed` for new sends; history stays readable for the counterpart. Blocking works both ways.
* Admin access: the queue shows only reason/reporter, never text. Opening a thread requires an existing report and is written to the
  audit log (`report_thread_viewed`) before content is returned. When a report names a message, the thread response marks it (`reported: true`) and the admin view highlights that line. There is no endpoint to browse arbitrary conversations.
* Retention: deleting an account removes the user's blocks and conversations/messages, **except conversations with an open report**
  (kept as abuse evidence until an admin resolves the report). Resolved reports stay as a record. Banning never deletes messages.
  There is no automatic purge job yet (tracked in HANDOFF.md).
* v1 has no attachments.

## Seller listings (session 9)
Page `/listings` (create, My listings, browse, detail with "Chat with seller"). API (all under `/api/v1`):
| Route | Auth | Notes |
|---|---|---|
| `GET /listings?page=n` | none (rate limited per IP) | 20 per page, newest first; only `status='active'` listings of `active` sellers; fields `ref, title, area, created_at, verified:false`; never the seller |
| `GET /listings/mine?page=&per_page=` | signed in | the caller's own listings (any status), newest first; `per_page` 1..50 (default 20); returns `{listings, total, page, per_page}`; the page UI shows 10 per page with Previous/Next |
| `POST /listings {title, area}` | signed in, not banned | `seller_id` is the session user; `ref` is generated (`u-…`), a client `ref`/`seller_id`/`status` is ignored |
| `GET /listings/by-ref/<ref>` | none | detail used by the page; includes `verified:false`, `contactable`, `own` |
| `POST /listings/<ref>/edit {title, area}` | owner only | session 15. Title 3..120, area 2..80 chars; control characters removed, whitespace collapsed. `ref`, `id`, `seller_id`, `status`, `verified` in the body are ignored |
| `POST /listings/<ref>/status {status}` | owner only | session 15. `active` (reopen) or `closed`; idempotent; nothing else is accepted |
Non-owners and unknown refs get the **same 404** (no probing). Banned/inactive sellers get 403 on create, edit and reopen (checked in the service as well as by the session guard). Rate limited with the `listing` bucket (`MESSAGE_RATE_LIMIT_PER_MIN`).
**Closed listings** disappear from `GET /listings`, `by-ref` reports `contactable:false`, `open_conversation` returns 404 `listing_unavailable` and sending in an existing conversation returns 409 `conversation_closed`. Existing conversations, messages, blocks and reports are **not touched**, and participants can still read them. Reopening restores everything.
**There is no delete.** See `docs/LISTING_DELETION_PROPOSAL.md`.
Seller-created listings are **unverified** and have only title + area (no price, photos or ownership check); the page says so. They are not connected to the CSV property data, because that would need an ownership-verification flow. Owners can edit title/area and close/reopen (session 15); there is no delete.

Conversation summaries now include `blocked_by_me` (only the caller's own block; the blocked person is never told). The Messages page uses an in-page `<dialog>` (Esc/Cancel/Confirm, focus handled by the browser) for Report, Block and Unblock instead of `prompt()`/`confirm()`; the report dialog requires a 3 to 500 character reason (the optional per-message selection is not offered in the UI; the API still accepts `message_id`).

## Retention
**Disabled by default.** No retention period has been approved, so `MESSAGE_RETENTION_DAYS=0` keeps everything. **The owner must decide the periods (and have them reviewed legally) before enabling this in production.** `REPORT_RETENTION_DAYS` defaults to 730 and is never shorter than the message period.

`python scripts/purge_messages.py` (dry run) / `--apply` (`--batch N`, default 1000 rows per step) runs `services/retention_service.py`:
1. resolved reports whose review is older than the report period are deleted;
2. messages older than the message period are deleted, **except** messages in a conversation that has an OPEN report and messages still referenced by any remaining report;
3. conversations left with no messages and no reports are deleted.
It never deletes users and never treats a ban as a reason to purge evidence. It prints/logs counts only, never message text. It is idempotent (re-running finds nothing more) and safe to interrupt (each step deletes in small chunks). Account deletion keeps its own rules (see above). Scheduling is **not** configured by this repository: call the script from Vercel Cron or any external scheduler once the period is approved, e.g. daily with `--apply`; repeat until it reports zeros if you have a large backlog. The SQL is plain parameterised `NOT EXISTS`/`IN`/`LIMIT` (SQLite-tested; not run on PostgreSQL here).
