"""The ?next= value the server puts on the login URL is a constant or one encoded same-site path, never user-controlled."""
import unittest
import warnings
from urllib.parse import parse_qs, urlparse

warnings.filterwarnings("ignore")

from tests.backend.test_auth import Client  # noqa: E402

EVIL = ("//evil.example", "https://evil.example", "/\\evil.example", "javascript:alert(1)")


def loc(r):
    return r.headers.get("Location", "")


class ReturnPathTests(unittest.TestCase):
    def test_user_supplied_next_is_never_copied_for_home_and_listings(self):
        c = Client(app_env="development")
        for evil in EVIL:
            self.assertEqual(loc(c.get(f"/?next={evil}")), "/login", evil)
            self.assertEqual(loc(c.get(f"/listings?next={evil}")), "/login?next=/listings", evil)

    def test_messages_return_path_is_one_encoded_same_site_value(self):
        # Regression: the raw query used to be copied with ?=& unescaped, so /messages?c=1&next=//evil produced a login URL with
        # two `next` parameters (harmless only because the client reads the first one).
        c = Client(app_env="development")
        for evil in EVIL:
            r = c.get(f"/messages?c=1&next={evil}")
            self.assertEqual(r.status_code, 302)
            u = urlparse(loc(r))
            self.assertEqual((u.scheme, u.netloc, u.path), ("", "", "/login"), evil)
            nxt = parse_qs(u.query)["next"]
            self.assertEqual(len(nxt), 1, f"duplicate next parameter for {evil}")
            self.assertTrue(nxt[0].startswith("/messages") and not nxt[0].startswith("//"), nxt[0])

    def test_plain_messages_return_path_still_works(self):
        c = Client(app_env="development")
        self.assertEqual(loc(c.get("/messages")), "/login?next=/messages")
        self.assertEqual(parse_qs(urlparse(loc(c.get("/messages?c=7"))).query)["next"], ["/messages?c=7"])


if __name__ == "__main__":
    unittest.main()
