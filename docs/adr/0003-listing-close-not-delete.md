# ADR 0003: Close/reopen instead of delete for listings
Status: accepted (session 15); soft delete proposed, not approved. Hard delete would orphan private conversations and moderation reports whose retention periods the owner has not decided. `status` (`active`/`closed`) is owner-controlled and reversible. See `docs/LISTING_DELETION_PROPOSAL.md`.
