"""Test-only dev server: the real app with an injected fake Google verifier (the credential string IS the nonce).
Used by tests/browser/cookies_test.py; never imported by the application. No network, no real Google."""
import time

from backend.app import app

CID = app.extensions["kpt"].settings.google_client_id


def _verify(credential, client_id):
    return {"aud": client_id, "iss": "https://accounts.google.com", "exp": time.time() + 600, "sub": "g-consent-test",
            "email": "gconsent@example.com", "email_verified": True, "name": "Google Consent", "nonce": credential}


app.extensions["kpt"].google_verifier = _verify

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=app.extensions["kpt"].settings.port, debug=False)
