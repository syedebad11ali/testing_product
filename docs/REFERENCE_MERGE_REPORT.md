# Reference merge report (WinRAR archive `karachi-property-trust__see_from_here_3.rar` into Session 23 master)

Master = `kpt-session23-merged.zip` (461 files). Reference = the RAR (13,466 extracted entries; `.git`, `node_modules` and every `.env*` file excluded and never opened).
Method: SHA-256 comparison of every reference file against the whole master tree (content, not path), then a manual review of every difference.

## Result in numbers (reference files, excluding .git / node_modules / .env*)
| Class | Files | Meaning |
|---|---|---|
| Byte-identical to a master file | 182 | Already present (photos, samples, fixtures, datasets' joblib etc.). Nothing to merge. |
| Same name, different content | 98 | 60 differ **only in line endings** (CRLF in the reference); 33 are real content differences (below); 5 binary/other. |
| Absent from the master | 21 | 11 standalone login demo, 3 old monolith sources, 4 old tests/results, 3 misc (below). |

## Decisions
| Reference item | Decision | Reason |
|---|---|---|
| Header **"Creators" menu** (`index.html`, `css/styles.css`) | **IMPORTED, adapted** | The only user-visible feature the master lacked. Rebuilt on the master's theme tokens with **initial avatars instead of `avatars.githubusercontent.com` images**, because the strict CSP (`img-src 'self' data: blob:`) must not be widened. Files: `frontend/index.html`, `css/creators.css`, `js/features/creators.js`, `js/main.js`. Dismiss on Escape / outside click / link click, focus returns to the pill. |
| `Chatbot/Login Page/**` (React + Express demo, `users.json`, JWT) | **Not imported** | Demo auth is weaker than the master's server sessions, scrypt, CSRF, lockout and rate limits. The master login already carries the reference design (nav, hero, icons, password toggle, Google, hex art) and goes further (remember-me, forgot/reset/change password, strength meter, field-level ARIA errors, busy state). |
| `public/assets/Dataset/*.csv` and `Chatbot/*.csv` | **Not imported (privacy)** | Reference CSVs contain `Owner ID`, `Owner Name`, `Property Owner`, `Previous Owner`. The master's public CSVs are deliberately sanitised. Compared by header names only; no rows were read or printed. |
| `js/app.js`, `css/styles.css`, `js/owner_verification.js` | Not imported | Old monolith ancestors of the master's modules. The featured carousel was already ported in an earlier step; `owner_verification.js` re-adds owner fields (privacy). |
| `js/extraction.js`, `tests/extraction.test.js` | Not imported | Same logic; the master is the ES-module port. |
| `price_prediction_pipeline.py` copies | Not imported | The master adds the pickle-compat alias (`sys.modules.setdefault`) the reference lacks. |
| `Chatbot/chatbot_core.py`, `app.py`, `chatbot.js`, `backup/**` | Not imported now | Ancestors; their useful parts were merged in earlier steps (see `docs/CHATBOT_REFERENCE_COMPARISON.md`). `backup/` is not authoritative. |
| `.vercelignore` / `.gitignore` / `vercel.json` / `pyproject.toml` | Nothing to import | Master already ignores `.env*`; `public/assets/Dataset` contains only the 5 CSVs; no reference-only dependency. |
| Old tests (`app_pipeline`, `manifest`, `owner_verification`, `manifest_results.json`) | Not imported | Test the old monolith; the master has module-level equivalents. |
| `.env` files in the reference (`Chatbot/.env`, `Chatbot/Login Page/.env`) | **Never read or packaged** | May contain live keys: rotate them. |

## Defects found and fixed during the merge
1. **Signup needed two clicks** (pre-existing in the merged master; `tests/browser/login_test.py` was failing on the untouched archive). The confirm-password blur check inserts an error line under the focused field the moment the submit button is pressed; the button moves between mouse-down and mouse-up and the click is lost. Fix: submit buttons no longer take focus on mouse press (`mousedown` default prevented in `frontend/js/auth-page.js`); keyboard/Tab behaviour and validation-on-submit are unchanged. Regression test: `tests/browser/signup_single_click_test.py` (fails on the old code, desktop case; passes now). `login_test.py` passes again.
2. `tests/backend/test_external_assets.py` (host guard) correctly flagged the new GitHub links. Added a **narrow** `OUTBOUND_LINK_HOSTS` allowlist (HTML `<a href>` only; asserted absent from the CSP) instead of loosening the guard; verified it still rejects a `github.com` `<img>`.

## Tests (Linux sandbox, Python 3.12.3, Node 22.22.2, Chromium, throwaway SQLite databases)
| Command | Before (untouched master) | After |
|---|---|---|
| `npm test` | 142 / 142 pass | **144 / 144 pass** (+2 `tests/frontend/creators.test.js`) |
| Python `unittest discover` | 228 run, 1 error | **229 run, 1 error** (+1 `test_outbound_link_hosts...`). The error is `test_admin_totp`: real `pyotp` is not installed (not a pass). |
| Browser | `login_test` FAILED | `creators_test`, `signup_single_click_test` (new), `csp_test`, `smoke`, `a11y_basics_test`, `featured_test`, `login_busy_test`, `property_images_test`, `login_test`, `cookies_test`, `prefs_test`, `messaging_test`, `listings_test`, `listing_lifecycle_test`, `camera_upload_test` all OK |

**Not run / limits:** `admin_totp_test` and `test_admin_totp` (no real `pyotp`); PostgreSQL; live Google OAuth and email; real OCR/PDF extraction (CDN libraries unavailable offline, `camera_upload_test` only proves graceful states); GitHub Actions; Windows; real touch devices. The 375 px emulation of the signup test also passes without the fix (layout does not move the button there), so the desktop case is the meaningful guard.

## Addendum: merge of `kpt-fixed-session22b-assets.zip`
Three-way merge (base = original Session 22, theirs = this upload, mine = Session 24 tree). The upload is the original Session 22 plus **108 asset files** (51 property photos, 57 sample documents) and edits to three docs. All 108 asset files are **byte-identical** to files already in this tree (SHA-256), so nothing was copied. `CHANGELOG.md`, `docs/DEPLOYMENT.md` and `docs/KNOWN_ISSUES.md` each had one conflict; resolved by hand keeping both sides. Their reported "blank navy promo thumbnail" was checked and is the original design, not a regression. Still open: the assets are unoptimised (about 96 MB + 77 MB).
