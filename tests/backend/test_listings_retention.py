"""Seller listing browse / My listings APIs, block state in the summary, and the message retention job."""
import time
import unittest
import unittest.mock
import warnings

warnings.filterwarnings("ignore")

from backend.services.retention_service import RetentionService  # noqa: E402
from tests.backend.test_moderation_messaging import PW, Peer, admin_post, uid, world  # noqa: E402

DAY = 86400


class ListingApiTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.p = world(message_rate_limit_per_min=1000)
        self.db = self.admin.app.extensions["kpt"].database()
        self.mk = lambda who, title, area="Gulshan": self.p[who].post("/api/v1/listings", {"title": title, "area": area})

    def test_create_requires_login_and_ignores_forged_identity(self):
        self.assertEqual(Peer(self.admin).post("/api/v1/listings", {"title": "House", "area": "DHA"}).status_code, 401)
        seller_id = uid(self.admin, "seller@example.com")
        r = self.p["seller"].post("/api/v1/listings", {"title": "3 Bed House", "area": "Gulshan", "seller_id": uid(self.admin, "buyer@example.com"),
                                                       "ref": "p1", "status": "active"})
        self.assertEqual(r.status_code, 201)
        listing = r.get_json()["listing"]
        self.assertTrue(listing["ref"].startswith("u-"), "a client-supplied ref must not be used")
        row = self.db.one("SELECT seller_id FROM listings WHERE ref = ?", (listing["ref"],))
        self.assertEqual(row["seller_id"], seller_id)

    def test_my_listings_are_paginated_bounded_and_owner_only(self):
        for i in range(25):
            self.mk("seller", f"Mine {i:02d}")
        self.mk("buyer", "Not mine")
        first = self.p["seller"].get("/api/v1/listings/mine?per_page=10").get_json()
        self.assertEqual((len(first["listings"]), first["total"], first["page"], first["per_page"]), (10, 25, 1, 10))
        last = self.p["seller"].get("/api/v1/listings/mine?per_page=10&page=3").get_json()
        self.assertEqual(len(last["listings"]), 5)
        seen = [x["ref"] for p in (1, 2, 3) for x in self.p["seller"].get(f"/api/v1/listings/mine?per_page=10&page={p}").get_json()["listings"]]
        self.assertEqual(len(seen), len(set(seen)), "no duplicates across pages")
        self.assertNotIn("Not mine", str(first) + str(last))
        self.assertEqual(self.p["seller"].get("/api/v1/listings/mine?per_page=9999").get_json()["per_page"], 50)   # clamped
        self.assertEqual(self.p["seller"].get("/api/v1/listings/mine?page=-4&per_page=0").get_json()["page"], 1)
        self.assertEqual(self.p["seller"].get("/api/v1/listings/mine?page=99").get_json()["listings"], [])
        self.assertEqual(self.p["buyer"].get("/api/v1/listings/mine").get_json()["total"], 1)

    def test_validation_is_server_side(self):
        for body in ({"title": "", "area": "DHA"}, {"title": "x" * 500, "area": "DHA"}, {"title": "ok title", "area": ""}, {"title": 5, "area": "DHA"}):
            self.assertEqual(self.p["seller"].post("/api/v1/listings", body).status_code, 400, body)

    def test_browse_is_public_paginated_and_hides_sellers(self):
        for i in range(23):
            self.mk("seller", f"Listing {i:02d}")
        anon = Peer(self.admin)
        first = anon.get("/api/v1/listings").get_json()
        self.assertEqual(len(first["listings"]), 20)
        self.assertTrue(first["has_more"])
        second = anon.get("/api/v1/listings?page=2").get_json()
        self.assertEqual(len(second["listings"]), 3)
        self.assertFalse(second["has_more"])
        refs = [x["ref"] for x in first["listings"] + second["listings"]]
        self.assertEqual(len(set(refs)), 23)
        self.assertTrue(all(x["verified"] is False for x in first["listings"]))
        text = str(first)
        self.assertNotIn("seller_id", text)
        self.assertNotIn(uid(self.admin, "seller@example.com"), text)
        self.assertNotIn("seller@example.com", text)

    def test_my_listings_is_owner_only(self):
        self.mk("seller", "Seller house")
        self.mk("buyer", "Buyer flat")
        mine = self.p["seller"].get("/api/v1/listings/mine").get_json()["listings"]
        self.assertEqual([x["title"] for x in mine], ["Seller house"])
        self.assertEqual(Peer(self.admin).get("/api/v1/listings/mine").status_code, 401)

    def test_inactive_listing_or_banned_seller_is_not_discoverable_or_contactable(self):
        ref = self.mk("seller", "Hidden soon").get_json()["listing"]
        lid = self.db.one("SELECT id FROM listings WHERE ref = ?", (ref["ref"],))["id"]
        self.assertIn(ref["ref"], str(Peer(self.admin).get("/api/v1/listings").get_json()))
        admin_post(self.admin, f"users/{uid(self.admin, 'seller@example.com')}/ban", kind="permanent", reason="spam listings")
        self.assertNotIn(ref["ref"], str(Peer(self.admin).get("/api/v1/listings").get_json()), "banned seller's listing must disappear")
        self.assertEqual(self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": lid}).status_code, 404)

    def test_banned_user_cannot_create_and_second_user_can_chat_about_a_new_listing(self):
        ref = self.mk("seller", "Chat target").get_json()["listing"]
        found = self.p["buyer"].get(f"/api/v1/listings/by-ref/{ref['ref']}").get_json()["listing"]
        self.assertTrue(found["contactable"])
        self.assertFalse(found["verified"])
        opened = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": found["id"]})
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(self.p["seller"].post("/api/v1/messages/conversations", {"listing_id": found["id"]}).get_json()["code"], "own_listing")
        admin_post(self.admin, f"users/{uid(self.admin, 'other@example.com')}/ban", kind="permanent", reason="abuse of service")
        self.assertIn(self.p["other"].post("/api/v1/listings", {"title": "Banned try", "area": "DHA"}).status_code, (401, 403))

    def test_conversation_summary_reports_only_my_own_block(self):
        ref = self.mk("seller", "Block target").get_json()["listing"]
        lid = self.db.one("SELECT id FROM listings WHERE ref = ?", (ref["ref"],))["id"]
        cid = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": lid}).get_json()["conversation"]["id"]
        get = lambda who: self.p[who].get(f"/api/v1/messages/conversations/{cid}").get_json()["conversation"]
        self.assertFalse(get("buyer")["blocked_by_me"])
        self.p["buyer"].post(f"/api/v1/messages/conversations/{cid}/block", {})
        self.assertTrue(get("buyer")["blocked_by_me"])
        self.assertFalse(get("seller")["blocked_by_me"], "the blocked person must not learn they were blocked via this flag")
        self.p["buyer"].post(f"/api/v1/messages/conversations/{cid}/unblock", {})
        self.assertFalse(get("buyer")["blocked_by_me"])


class RetentionTests(unittest.TestCase):
    NOW = 2_000_000_000

    def setUp(self):
        self.admin, self.p = world()
        self.db = self.admin.app.extensions["kpt"].database()
        self.svc = RetentionService(self.db)
        self.seller, self.buyer = uid(self.admin, "seller@example.com"), uid(self.admin, "buyer@example.com")

    def conv(self, cid, age_days, bodies=1):
        self.db.execute("INSERT INTO listings (id, ref, seller_id, title, area, status, created_at) VALUES (?,?,?,?,?,?,?)",
                        (f"l{cid}".ljust(32, "0"), f"r{cid}", self.seller, "t", "a", "active", self.NOW - age_days * DAY))
        cid32 = f"c{cid}".ljust(32, "0")
        self.db.execute("INSERT INTO conversations (id, listing_id, buyer_id, seller_id, created_at, last_message_at) VALUES (?,?,?,?,?,?)",
                        (cid32, f"l{cid}".ljust(32, "0"), self.buyer, self.seller, self.NOW - age_days * DAY, self.NOW - age_days * DAY))
        for i in range(bodies):
            self.db.execute("INSERT INTO messages (id, conversation_id, sender_id, body, ts) VALUES (?,?,?,?,?)",
                            (f"m{cid}{i}".ljust(32, "0"), cid32, self.buyer, f"secret body {cid}{i}", (self.NOW - age_days * DAY) * 1_000_000 + i))
        return cid32

    def report(self, cid32, status="open", age_days=0, msg=None):
        rid = f"r{cid32[:6]}{status}".ljust(32, "0")
        self.db.execute("INSERT INTO message_reports (id, conversation_id, message_id, reporter_id, reason, created_at, status, reviewed_at) VALUES (?,?,?,?,?,?,?,?)",
                        (rid, cid32, msg, self.buyer, "bad", self.NOW - age_days * DAY, status, self.NOW - age_days * DAY if status == "resolved" else None))
        return rid

    def count(self, table):
        return self.db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]  # noqa: S608

    def test_disabled_by_default_changes_nothing(self):
        self.conv("a", 900)
        self.assertEqual(self.svc.run(0, 730, apply=True, now=self.NOW), {"applied": True, "enabled": False, "reports": 0, "messages": 0, "conversations": 0})
        self.assertEqual(self.count("messages"), 1)

    def test_dry_run_counts_but_deletes_nothing(self):
        self.conv("old", 400, bodies=3); self.conv("new", 10)
        out = self.svc.run(365, 730, apply=False, now=self.NOW)
        self.assertEqual((out["messages"], out["applied"]), (3, False))
        self.assertEqual(self.count("messages"), 4)

    def test_cutoff_and_idempotency(self):
        self.conv("old", 400, bodies=3); self.conv("new", 10)
        first = self.svc.run(365, 730, apply=True, now=self.NOW)
        self.assertEqual((first["messages"], first["conversations"]), (3, 1))      # old messages, then the conversation they emptied
        self.assertEqual(self.count("messages"), 1)
        second = self.svc.run(365, 730, apply=True, now=self.NOW)
        self.assertEqual((second["messages"], second["conversations"]), (0, 0))
        third = self.svc.run(365, 730, apply=True, now=self.NOW)
        self.assertEqual((third["messages"], third["conversations"], third["reports"]), (0, 0, 0))
        self.assertEqual(self.count("conversations"), 1, "the recent conversation must survive")

    def test_open_report_protects_the_whole_conversation(self):
        c = self.conv("evid", 900, bodies=2)
        self.report(c, "open", age_days=5)
        out = self.svc.run(365, 730, apply=True, now=self.NOW)
        self.assertEqual((out["messages"], out["conversations"]), (0, 0))
        self.assertEqual(self.count("messages"), 2)

    def test_resolved_report_is_purged_after_its_period_and_then_messages_follow(self):
        c = self.conv("res", 900, bodies=2)
        self.report(c, "resolved", age_days=800)
        out = self.svc.run(365, 730, apply=True, now=self.NOW)
        self.assertEqual((out["reports"], out["messages"]), (1, 2))   # evidence protection ends with the report, in the same pass
        self.assertEqual(self.count("messages"), 0)

    def test_recently_resolved_report_keeps_its_referenced_message(self):
        c = self.conv("ref", 900, bodies=2)
        keep = f"m{'ref'}0".ljust(32, "0")
        self.report(c, "resolved", age_days=30, msg=keep)
        self.svc.run(365, 730, apply=True, now=self.NOW)
        remaining = [r["id"] for r in self.db.all("SELECT id FROM messages WHERE conversation_id = ?", (c,))]
        self.assertEqual(remaining, [keep])

    def test_batch_bounds_one_run(self):
        self.conv("big", 900, bodies=5)
        self.assertEqual(self.svc.run(365, 730, batch=2, apply=True, now=self.NOW)["messages"], 2)
        self.assertEqual(self.count("messages"), 3)

    def test_banning_a_user_does_not_make_their_messages_eligible(self):
        self.conv("fresh", 10, bodies=2)
        admin_post(self.admin, f"users/{self.buyer}/ban", kind="permanent", reason="spam listings")
        self.assertEqual(self.svc.run(365, 730, apply=True, now=self.NOW)["messages"], 0)

    def test_script_is_disabled_without_configuration_and_never_prints_bodies(self):
        import contextlib, io, os
        from scripts import purge_messages
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), unittest.mock.patch.dict(os.environ, {"MESSAGE_RETENTION_DAYS": "0"}):
            self.assertEqual(purge_messages.main([]), 0)
        self.assertIn("disabled", buf.getvalue())
        self.assertNotIn("secret body", buf.getvalue())


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
