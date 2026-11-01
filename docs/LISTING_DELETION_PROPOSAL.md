# Proposal: removing a seller listing (not implemented)

**Status:** design only. No delete route, button or SQL exists; session 15 shipped reversible close/reopen instead.

## Why not a hard delete
`conversations.listing_id` points at `listings.id`; messages and `message_reports` hang off conversations. Deleting the row would orphan or cascade-delete private messages and moderation evidence, which conflicts with the report-retention rules the owner has not yet approved (`MESSAGE_RETENTION_DAYS=0`; the 730-day report default is NOT approved policy). It would also free the `ref`, letting a later listing reuse a ref people may have bookmarked.

## Proposed soft delete (needs owner approval)
1. Add `deleted_at BIGINT NULL` (and optional `deleted_by`) via a new migration; keep `status` for active/closed.
2. Owner-only `POST /listings/<ref>/remove`: sets `deleted_at`, forces `status='closed'`; 404 for non-owners (same as today); audited (`listing_removed`, no body text).
3. Removed listings: hidden from browse, `by-ref` and "My listings" (or shown under a collapsed "Removed" heading with Restore for N days); no new conversations; existing conversations stay readable by participants, marked "listing removed".
4. Restore within a grace window (owner decision, e.g. 30 days); after that an approved retention job may anonymise title/area (`'[removed]'`) but keeps the row, `ref`, and anything referenced by an open report.
5. Account deletion later: same approach, anonymise rather than cascade.

## Decisions the owner must make
Grace period; whether participants keep access to old conversations; what moderators may see after removal; legal retention for reports/messages; whether title/area are personal data that must be erased on request.

## Tests to add when built
IDOR (non-owner 404), banned seller refused, removed listing absent from every public surface, conversations/messages/reports preserved, restore, ref never reused, audit row written without content.
