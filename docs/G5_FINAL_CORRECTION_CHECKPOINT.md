# G5 final correction checkpoint

**Scope:** one stale browser test. Nothing else.

**Problem:** `tests/browser/prefs_test.py` still expected the obsolete G5.2 behavior (a guest's home filters persisted in `kpt_prefs` and restored after reload when Preferences consent was given). G5.3a-c made guests never persist or restore filters.

**Change (test only):** for both consent choices the guest case now checks that filtering works immediately (fewer cards shown), that the filters are not restored after reload, that `kpt_prefs` carries no filter keys, and (reject) that no `kpt_prefs` cookie exists. Tampered-cookie check kept as it was. Docstring updated. `CHANGELOG.md` gained one line; `G5_FINAL_REPORT.md` (root and `docs/`) was updated.

**Not changed:** application code, CSS, favorites, authentication, the preferences API, other tests, migrations.

**Results:** `prefs_test.py` OK; `g5_account_data_test.py` OK; `tests.backend.test_ci_config` 6 tests OK. Nothing else was run in this step.

**Still open (unchanged):** `pyotp` missing (`test_admin_totp`, `admin_totp_test`), pre-existing `camera_upload_test` and `creators_test` failures, parallel-load timeouts, no GitHub CI run.
