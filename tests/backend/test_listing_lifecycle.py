"""Session 15: owner-only edit (title/area) and reversible close/reopen. No hard delete exists."""
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_moderation_messaging import Peer, uid, world  # noqa: E402

API = "/api/v1/listings"


class ListingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.p = world(message_rate_limit_per_min=1000)
        self.db = self.admin.app.extensions["kpt"].database()
        self.ref = self.p["seller"].post(API, {"title": "3 Bed House", "area": "Gulshan"}).get_json()["listing"]["ref"]

    def edit(self, who, _ref=None, **body):
        return self.p[who].post(f"{API}/{_ref or self.ref}/edit", body)

    def status(self, who, st, ref=None):
        return self.p[who].post(f"{API}/{ref or self.ref}/status", {"status": st})

    def test_owner_edits_title_and_area_only(self):
        before = self.db.one("SELECT id, ref, seller_id, status FROM listings WHERE ref = ?", (self.ref,))
        r = self.edit("seller", title="  4  Bed\x00 Villa ", area="DHA", ref="hijack", seller_id="x", status="closed", verified=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["listing"]["title"], r.get_json()["listing"]["area"]), ("4 Bed Villa", "DHA"))
        after = self.db.one("SELECT id, ref, seller_id, status, title FROM listings WHERE id = ?", (before["id"],))
        self.assertEqual((after["ref"], after["seller_id"], after["status"]), (before["ref"], before["seller_id"], "active"))
        self.assertFalse(r.get_json()["listing"]["verified"])

    def test_non_owner_and_unknown_ref_get_identical_404(self):
        a, b = self.edit("buyer", title="Hacked", area="X1"), self.edit("buyer", _ref="u-doesnotexist", title="Hacked", area="X1")
        self.assertEqual((a.status_code, b.status_code), (404, 404))
        self.assertEqual({k: v for k, v in a.get_json().items() if k != "request_id"}, {k: v for k, v in b.get_json().items() if k != "request_id"})
        self.assertEqual(self.status("buyer", "closed").status_code, 404)
        self.assertEqual(self.status("other", "active").status_code, 404)
        self.assertEqual(self.db.one("SELECT title, status FROM listings WHERE ref = ?", (self.ref,))["title"], "3 Bed House")
        self.assertEqual(self.db.one("SELECT status FROM listings WHERE ref = ?", (self.ref,))["status"], "active")

    def test_anonymous_and_csrf(self):
        anon = Peer(self.admin)
        self.assertEqual(anon.post(f"{API}/{self.ref}/edit", {"title": "abc", "area": "DHA"}).status_code, 401)
        self.assertEqual(self.p["seller"].post(f"{API}/{self.ref}/status", {"status": "closed"}, token=None).status_code, 403)

    def test_invalid_input(self):
        for body in ({}, {"title": "ab", "area": "DHA"}, {"title": "x" * 121, "area": "DHA"}, {"title": "Good", "area": "D"},
                     {"title": "Good", "area": "x" * 81}, {"title": 5, "area": "DHA"}, {"title": ["a"], "area": "DHA"}, {"title": "\x00\x01  ", "area": "DHA"}):
            self.assertEqual(self.edit("seller", **body).status_code, 400, body)
        for st in ("deleted", "", None, 1, "ACTIVE"):
            self.assertEqual(self.p["seller"].post(f"{API}/{self.ref}/status", {"status": st}).status_code, 400, st)
        self.assertEqual(self.p["seller"].post(f"{API}/bad%20ref!/edit", {"title": "abc", "area": "DHA"}).status_code, 404)

    def test_close_reopen_browse_and_conversations(self):
        listing_id = self.db.one("SELECT id FROM listings WHERE ref = ?", (self.ref,))["id"]
        conv = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": listing_id})
        self.assertEqual(conv.status_code, 200)
        cid = conv.get_json()["conversation"]["id"]
        self.assertEqual(self.p["buyer"].post(f"/api/v1/messages/conversations/{cid}/messages", {"body": "hello"}).status_code, 201)
        self.assertEqual(self.status("seller", "closed").status_code, 200)
        self.assertEqual(self.status("seller", "closed").status_code, 200, "idempotent")
        refs = [x["ref"] for x in self.p["other"].get(API).get_json()["listings"]]
        self.assertNotIn(self.ref, refs)
        self.assertIn(self.ref, [x["ref"] for x in self.p["seller"].get(f"{API}/mine").get_json()["listings"]])
        self.assertEqual(self.p["other"].post("/api/v1/messages/conversations", {"listing_id": listing_id}).status_code, 404)
        self.assertEqual(self.p["buyer"].post(f"/api/v1/messages/conversations/{cid}/messages", {"body": "again"}).status_code, 409)
        self.assertFalse(self.p["other"].get(f"{API}/by-ref/{self.ref}").get_json()["listing"]["contactable"])
        # existing conversation + messages preserved and readable
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (cid,))["n"], 1)
        self.assertEqual(self.p["buyer"].get(f"/api/v1/messages/conversations/{cid}").status_code, 200)
        # reopen
        self.assertEqual(self.status("seller", "active").status_code, 200)
        self.assertIn(self.ref, [x["ref"] for x in self.p["other"].get(API).get_json()["listings"]])
        self.assertEqual(self.p["other"].post("/api/v1/messages/conversations", {"listing_id": listing_id}).status_code, 200)

    def test_banned_seller_cannot_edit_reopen_or_create(self):
        self.status("seller", "closed")
        sid = uid(self.admin, "seller@example.com")
        self.db.execute("UPDATE users SET status = 'banned' WHERE id = ?", (sid,))
        self.assertIn(self.status("seller", "active").status_code, (401, 403))
        self.assertIn(self.edit("seller", title="Still me", area="DHA").status_code, (401, 403))
        self.assertIn(self.p["seller"].post(API, {"title": "New one", "area": "DHA"}).status_code, (401, 403))
        self.assertEqual(self.db.one("SELECT status FROM listings WHERE ref = ?", (self.ref,))["status"], "closed")
        # service-level guard even if a session slipped through
        from backend.errors import ApiError
        svc = self.admin.app.extensions["kpt"].messaging()
        for fn in (lambda: svc.set_listing_status(sid, self.ref, "active"), lambda: svc.update_listing(sid, self.ref, "abc", "DHA"),
                   lambda: svc.create_listing(sid, "New one", "DHA")):
            with self.assertRaises(ApiError) as cm:
                fn()
            self.assertEqual(cm.exception.status, 403)

    def test_no_delete_route(self):
        for m in ("delete", "put", "patch"):
            self.assertIn(getattr(self.p["seller"].c, m)(f"{API}/{self.ref}", base_url="https://localhost").status_code, (403, 404, 405))
        self.assertIsNotNone(self.db.one("SELECT id FROM listings WHERE ref = ?", (self.ref,)))


if __name__ == "__main__":
    unittest.main()
