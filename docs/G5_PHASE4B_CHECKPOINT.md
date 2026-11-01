# G5.4b checkpoint - stale favorites CSS expectation

**Base:** the G5.4a working tree (G5.1 to G5.4a preserved). Patch is relative to it.

## Inspection
* `frontend/css/base.css` line 35: `:root[data-theme="dark"] .favorite-heart{-webkit-text-stroke:0.5px #011425;}`; line 36: `.saved .favorite-heart{-webkit-text-stroke:0;}`. Unchanged.
* `tests/frontend/favorites.test.js` line 87 still expected `-webkit-text-stroke:1px #000`, so the third test ("favorite gradients use blue in light theme, green in dark theme, and pink-red hearts") failed. This is the failure listed as pre-existing since the G4 audit and G5.3c.

## Change (one line, test only)
`tests/frontend/favorites.test.js` line 87: the expected pattern is now `-webkit-text-stroke:0\.5px #011425;?` (was `1px #000`). Line endings (CRLF) preserved. No CSS, application code or other test was touched. The `.saved` expectation on line 88 already matched the CSS and is unchanged.

## Actual results

| Command | Result |
| --- | --- |
| `node --test tests/frontend/favorites.test.js` | 3 run, 3 pass, 0 fail (before the edit: 2 pass, 1 fail) |
| `node --test tests/frontend/favoritesAuthGate.test.js` | 8 run, 8 pass, 0 fail |
| `node --test tests/frontend/favoritesServer.test.js` | 15 run, 15 pass, 0 fail |

Not run, as instructed: the full suite, browser tests, backend tests.

## Patch
`g5-phase4b.patch`: 1 file, 1 line changed, `-p1`, relative to the G5.4a tree. Verified: applies cleanly to the G5.4a copy of the test file and reproduces the edited file byte for byte.

The "favorites dark-heart assertion" is no longer a known failing test.

STOP after G5.4b.
