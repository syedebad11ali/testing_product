"""Shared step for browser tests. Since T4 the application pages need a server-side session, so a test that wants the app enters
through the real "Continue as Guest" button on the login page (this also exercises that flow) instead of opening "/" anonymously.

Since T5a the cookie banner is NOT shown on the entry pages (/login, /signup, /developer-login, /nice-try); it appears on the first
page after sign-in / guest entry when no choice is recorded, so the helpers dismiss it there."""


def dismiss_consent(page, choice="reject", wait_ms=0):
    """Dismiss the cookie banner if it is present (optionally waiting up to wait_ms for it to appear)."""
    if wait_ms:
        try:
            page.wait_for_selector(f"[data-choice={choice}]", state="visible", timeout=wait_ms)
        except Exception:  # noqa: BLE001 - no banner: a choice may already be recorded
            return
    btn = page.query_selector(f"[data-choice={choice}]")
    if btn and btn.is_visible():
        btn.click()


def enter_as_guest(page, base, dest="/", dismiss=True):
    page.goto(base + "/login")
    page.wait_for_selector("#guest-btn")
    page.click("#guest-btn")
    page.wait_for_url(base + dest)
    if dismiss:
        dismiss_consent(page, wait_ms=3000)  # T5a: the banner appears after guest entry, not on /login
    return page


USER_PASSWORD = "quartz-lantern-harbor-91"   # throwaway test password (passes the strength rules; never a real credential)


def enter_as_user(page, base, email=None, name="Test Person", password=USER_PASSWORD, dest="/", dismiss=True):
    """Register a NEW account through the real sign-up form and land on the app as a registered user (G4a3).
    Use this for tests that exercise account-only features such as the chatbot; guests are refused those since G2/G4.
    The e-mail is unique per call. Returns the e-mail so a test can log in again."""
    import uuid
    email = email or f"user{uuid.uuid4().hex[:10]}@example.com"
    page.goto(base + "/signup")
    page.wait_for_selector("#su-name")
    page.fill("#su-name", name); page.fill("#su-email", email)
    page.fill("#su-pw", password); page.fill("#su-confirm", password)
    page.click("#form-signup button[type=submit]")
    page.wait_for_url(base + dest)
    if dismiss:
        dismiss_consent(page, wait_ms=3000)
    return email
