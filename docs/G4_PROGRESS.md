# G4 progress checkpoint (recovery file; updated after each phase)
Baseline: `karachi-property-trust-G4a2.zip` (G2, G3, G4a1, G4a2 present; verified at start of this run).
Working dir: /home/claude/g4/kpt; pristine baseline copy: /home/claude/g4base/kpt (for the final patch).

| Phase | Status | Notes |
|---|---|---|
| Baseline verified | [x] | require_account, chat.py guards, chat.js launch guard, chatApi.js auth errors, loginPrompt, sessionUser, router guest gate all present |
| A  G4a main chatbot verify | [x] | all launch paths go through guarded `openChat()`; the 'Ask the assistant' browser step was previously skipped silently (`if asks.count()`), corrected in G4b: now unconditional and passing for guest and registered user |
| B  G4a3 browser regression | [x] | NEW `tests/browser/g4_chatbot_test.py` (28 checks OK; fails when the guard is removed); `tests/browser/support/session_entry.py` + `enter_as_user()`; `tests/browser/smoke.py` now uses a registered user (was failing at the chat step); `cookies_test.py` unchanged (already chats after a real sign-up; passes); registered in `.github/workflows/ci.yml`; `test_ci_config` OK |
| C  G4b widget | [x] | `frontend/widget/chatbot.js` + `chatbot.css`: 401 `auth_required` / 403 `guest_not_allowed` -> one fixed "Login required" card (`Create an account or log in to use this feature.`, `Log in / Sign up`); 403 `password_change_required` -> "Password change required" card to `/login?change=1`; login link = script-origin (KPT) + `/login?next=%2Fchatbot-demo` (never `cfg.apiUrl`); third-party embeds open it in a new tab with a not-signed-in-here note; composer locked, no retry/resend, rejected message dropped, one prompt; unrelated 403s/429/5xx/network/timeout keep the old error row + Try again |
| D  widget tests | [x] | NEW `tests/browser/widget_auth_test.py` (58 checks, mocked API, first + third party host, 320-1280 px), NEW `tests/browser/g4_widget_test.py` (21 checks, real backend, real cross-origin embed); `g4_chatbot_test.py` 'Ask the assistant' step now unconditional on a real listing (DEMO-KPT-1648) for guest + registered; `csp_test.py` widget assertion tightened (anonymous: login card; registered: real non-error answer with source line); both new tests registered in `.github/workflows/ci.yml`, `test_ci_config` OK |
| E  regression runs | [x] | see evidence in `docs/GUEST_BROWSE_ONLY_PLAN.md` G4 entry; one self-inflicted failure found and fixed (`test_text_encoding`: new test read files without `encoding=`) |
| F  security review | [x] | no backend/cookie/CORS change (diff vs G4a: widget, tests, CI, docs only); login origin from `script.src` only (http/https, else relative); card via `textContent`; fixed `next`; third-party link `target=_blank rel=noopener noreferrer`; no inline styles (CSS classes only; csp_test passes) |
| G  docs | [x] | plan, work.md, HANDOFF.md, CHANGELOG.md, CHATBOT.md, AUTH.md, this file; stale 'G4a3 not started' and 'G4 stays OPEN' statements corrected |
| Packaging | [x] | `karachi-property-trust-G4-complete.zip` (single `kpt/` root) + `.patch` (applies to the G4a checkpoint with `patch -p1`); hashes are in the final report |

## Files changed so far (vs G4a2 baseline)
`tests/browser/support/session_entry.py`, `tests/browser/smoke.py`, `.github/workflows/ci.yml`, NEW `tests/browser/g4_chatbot_test.py`, NEW `docs/G4_PROGRESS.md`. No application source changed in phase A/B (G4a1/G4a2 code verified correct).

## Owner decision (applied)
No credentialed cross-origin auth for third-party embeds: cookies stay SameSite=Lax, CORS unchanged, no second auth mechanism. A third-party embedded widget therefore ALWAYS shows the login card (even for a user logged in on KPT); authenticated chat works only on KPT's own site (`/chatbot-demo` or the main app).

## Files changed in G4b (vs G4a checkpoint)
`frontend/widget/chatbot.js`, `frontend/widget/chatbot.css`, `tests/browser/g4_chatbot_test.py`, `tests/browser/csp_test.py`, `.github/workflows/ci.yml`, NEW `tests/browser/widget_auth_test.py`, NEW `tests/browser/g4_widget_test.py`, `docs/G4_PROGRESS.md`.

## Remaining
E (regression runs), F (security review), G (docs: plan, work.md, HANDOFF.md, CHANGELOG.md, CHATBOT.md/AUTH.md notes), final ZIP + patch. Recovery: this checkpoint ZIP is complete and runnable.
