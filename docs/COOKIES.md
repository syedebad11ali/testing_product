# Cookies

Kept in sync with the code (`backend/security/cookies.py`, `consent.py`, `services/remember_service.py`).
Names get the `__Host-` prefix when `COOKIE_SECURE` is on (production / https); plain-http local development uses unprefixed names.

| Cookie | Category | Purpose | Lifetime | Flags | Set by |
|---|---|---|---|---|---|
| `__Host-kpt_session` | Essential | Server-side session id (only its hash is stored) | browser session (server idle/absolute limits) | HttpOnly, Secure, SameSite=Lax, Path=/ | server |
| `__Host-kpt_csrf` | Essential | CSRF double-submit token | browser session | Secure, SameSite=Lax, Path=/ (JS-readable by design) | server |
| `kpt_consent` | Essential | Consent record `v=<policy version>&p=<0/1>&a=<0/1>` | 12 months | Secure, SameSite=Lax | browser (`features/consent.js` banner, `core/cookies.js`) |
| `__Host-kpt_remember` | Preferences | "Remember me": `selector.validator`, rotated on every use | 30 days (`REMEMBER_DAYS`) | HttpOnly, Secure, SameSite=Lax, Path=/ | server, only after Preferences consent and an explicit "Remember me" |
| `__Host-kpt_chat` | Preferences | Random id of the anonymous chat conversation | 7 days (`CHAT_COOKIE_DAYS`) | HttpOnly, Secure, SameSite=Lax, Path=/ | server, only after Preferences consent |
| `kpt_prefs` | Preferences | Short codes/ids: theme, language, filters, sort, recently viewed, compare, saved, dismissed hints | 6 months | Secure, SameSite=Lax | browser (`core/cookies.js`; the theme toggle writes it) |

Rules: no names, emails, tokens, roles or free text in any cookie; `kpt_prefs` is validated and clamped on every read
(`services/prefs.py`); the server ignores `kpt_prefs` and sets no optional cookie unless `kpt_consent` is current and allows it.
Admins never receive a remember token. Changing a password, resetting it, disabling a user or "log out everywhere" revokes every remember token.

## Browser side
* `js/core/cookies.js` is the only code that writes `kpt_consent` and `kpt_prefs`. It URL-encodes values, never throws, and writes `kpt_prefs` only when the visitor allowed Preferences; otherwise choices (e.g. the theme) are kept in memory for the current visit. Declining or withdrawing Preferences deletes `kpt_prefs` at once.
* `js/core/prefs.js` mirrors `services/prefs.py`; both run `tests/shared/prefs_cases.json`. Cookie content is untrusted: unknown keys, free text and out-of-range values are dropped.
* Theme: `js/theme-init.js` (a blocking external script, so the CSP needs no inline-script allowance) reads `kpt_prefs` before first paint. `localStorage` is no longer used for UI preferences.
* Banner: `features/consent.js` (started by `main.js` on `/`, or by `consent-banner.js` on `/listings`, `/messages`, `/admin`, `/privacy`). **T5a:** the entry pages `/login` (also serves `/signup`), `/developer-login` and `/nice-try` do not load it, so the banner first appears on the page after password login, sign-up, Google sign-in or Continue as guest, and only when no current choice exists. Consequence: on a first visit "Remember me" at login finds no Preferences consent, so no remember token is issued and the login response carries `remember_note` (existing behaviour); an earlier saved choice works as before. No analytics or marketing script exists in `frontend/`. "Reject non-essential" and "Accept all" have equal weight. Bumping `COOKIE_POLICY_VERSION` (in `backend/security/consent.py` **and** `core/cookies.js`, a test checks they match) asks everyone again.
* Privacy page `/privacy`: the table in `frontend/privacy.html` must list exactly the cookies in the table above (a test enforces it).
* After login the browser's `kpt_prefs` and the account's saved prefs are merged (`services/accountApi.js: syncPrefsAfterLogin`).
* Category choice for "Remember me": it is a Preferences cookie and is issued only after the visitor ticks the box *and* allowed Preferences; otherwise the login response carries `remember_note` and the UI explains why.


## Home filters and sort (session 10)
With **Preferences** consent, the Home screen's area chip, type select and sort select are saved in `kpt_prefs` as the short codes `area`, `ptype` and `sort` (`newest`, `price_asc`, `price_desc`) and restored on the next visit (`frontend/js/features/homePrefs.js`). Rules: values are only used to *select* one of the options the page really offers (case-insensitive match; anything else is ignored); the free-text search box is never stored; "Largest Property" has no cookie code, so it is not remembered; without consent the choice lasts for the current visit only (memory). Dismissed hints deliberately stay in `sessionStorage` (session-scoped, never persistent), so they cannot be used to get around a rejected Preferences choice.

## Consent banner placement (session 12 follow-up)
While the banner is open it no longer hides the bottom of the page: `features/consent.js` adds `body.has-consent` and sets `--consent-h` to the banner's height (following wrapping, rotation and the expanded "Customise" view), and `consent.css` turns that into bottom padding. Both are removed on every choice. The banner is capped at 70% of the viewport and scrolls inside itself, so the buttons stay reachable on small screens. "Reject non-essential" and "Accept all" keep identical size and weight; nothing about the consent semantics changed.
