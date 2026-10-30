"""Phase 4 (admin moderation / bans) and Phase 5 (buyer-seller messaging): API + service + DB, two accounts, one app."""
import re
import time
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import ADMIN_PW, BASE, Client  # noqa: E402

PW = "correct-horse-battery"


class Peer(Client):
    """Another browser on the SAME app/database (own cookie jar and CSRF token)."""

    def __init__(self, other):
        self.app, self.c = other.app, other.app.test_client()
        self.token = self.c.get("/api/v1/auth/csrf", base_url=BASE).get_json()["csrf_token"]


def world(**overrides):
    admin = Client(**overrides)
    assert admin.login("admin_001", ADMIN_PW).status_code == 200
    people = {}
    for key, email in (("seller", "seller@example.com"), ("buyer", "buyer@example.com"), ("other", "other@example.com")):
        p = Peer(admin)
        assert p.signup(email=email, pw=PW, name=f"{key.title()} Person").status_code in (200, 201)
        people[key] = p
    return admin, people


def uid(admin, email):
    return admin.app.extensions["kpt"].database().one("SELECT id FROM users WHERE email = ?", (email,))["id"]


def admin_post(admin, path, **body):
    return admin.post(f"/api/v1/admin/{path}", {"password": ADMIN_PW, **body})


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.p = world()
        self.buyer_id = uid(self.admin, "buyer@example.com")
        self.db = self.admin.app.extensions["kpt"].database()

    def test_only_admins_reach_admin_endpoints(self):
        for who in (Peer(self.admin), self.p["buyer"]):
            for path in ("users", "login-events", "audit", "sessions", "export/users.csv", "reports"):
                self.assertIn(who.get(f"/api/v1/admin/{path}").status_code, (401, 403), path)
            for path in (f"users/{self.buyer_id}/ban", f"users/{self.buyer_id}/unban", f"users/{self.buyer_id}/role", f"users/{self.buyer_id}/logout"):
                self.assertIn(who.post(f"/api/v1/admin/{path}", {"password": PW, "reason": "x y z", "kind": "permanent"}).status_code, (401, 403), path)

    def test_ban_needs_reason_and_password_then_blocks_everything(self):
        url = f"users/{self.buyer_id}/ban"
        self.assertEqual(admin_post(self.admin, url, kind="permanent").get_json()["code"], "reason_required")
        self.assertEqual(self.admin.post(f"/api/v1/admin/{url}", {"kind": "permanent", "reason": "spam listings", "password": "wrong"}).status_code, 403)
        buyer = self.p["buyer"]
        self.assertIsNotNone(buyer.get("/api/v1/auth/me").get_json()["user"])
        r = admin_post(self.admin, url, kind="permanent", reason="spam listings")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNone(buyer.get("/api/v1/auth/me").get_json()["user"])  # open session died at once
        self.assertEqual(buyer.get("/api/v1/messages/conversations").status_code, 401)
        self.assertEqual(buyer.post("/api/v1/listings", {"title": "x", "area": "y"}).status_code, 401)
        self.assertEqual(Peer(self.admin).login("buyer@example.com", PW).status_code, 401)
        denied = self.db.one("SELECT success FROM login_events WHERE user_id = ? AND reason = 'banned'", (self.buyer_id,))
        self.assertEqual(denied["success"], 0)  # the failed attempt is recorded with the reason
        audit = self.db.one("SELECT actor_id, action, detail FROM audit_log WHERE target = ? AND action = 'user_banned'", (self.buyer_id,))
        self.assertIn("spam listings", audit["detail"])
        self.assertEqual(self.admin.post(f"/api/v1/admin/{url}", {"kind": "permanent", "reason": "again", "password": ADMIN_PW}).status_code, 409)

    def test_ban_revokes_remember_tokens(self):
        c = Peer(self.admin)
        c.c.set_cookie("kpt_consent", "v=1&p=1&a=0", domain="localhost")
        c.post("/api/v1/auth/login", {"identifier": "sara@example.com", "password": PW, "remember": True})  # no such user: nothing issued
        self.db.execute("INSERT INTO remember_tokens (id, selector, validator_hash, user_id, device_label, created_at, last_used_at, expires_at) VALUES ('t1','s1','h',?,?,1,1,9999999999)", (self.buyer_id, "x"))
        admin_post(self.admin, f"users/{self.buyer_id}/ban", kind="permanent", reason="abuse reports")
        self.assertIsNotNone(self.db.one("SELECT revoked_at FROM remember_tokens WHERE id = 't1'")["revoked_at"])

    def test_temporary_suspension_expires_and_is_logged(self):
        admin_post(self.admin, f"users/{self.buyer_id}/ban", kind="temporary", days=2, reason="cooling off")
        self.assertEqual(Peer(self.admin).login("buyer@example.com", PW).status_code, 401)
        self.db.execute("UPDATE user_bans SET expires_at = ? WHERE user_id = ?", (int(time.time()) - 5, self.buyer_id))
        again = Peer(self.admin)
        self.assertEqual(again.login("buyer@example.com", PW).status_code, 200)
        self.assertEqual(self.db.one("SELECT status FROM users WHERE id = ?", (self.buyer_id,))["status"], "active")
        self.assertEqual(self.db.one("SELECT lift_reason FROM user_bans WHERE user_id = ?", (self.buyer_id,))["lift_reason"], "expired")
        self.assertTrue(self.db.one("SELECT 1 AS x FROM audit_log WHERE action = 'ban_expired' AND target = ?", (self.buyer_id,)))

    def test_bad_ban_parameters(self):
        url = f"users/{self.buyer_id}/ban"
        for body in ({"kind": "forever"}, {"kind": "temporary"}, {"kind": "temporary", "days": 0}, {"kind": "temporary", "days": 400}, {"kind": "temporary", "days": True}):
            self.assertEqual(admin_post(self.admin, url, reason="valid reason", **body).status_code, 400, body)
        self.assertEqual(self.db.one("SELECT status FROM users WHERE id = ?", (self.buyer_id,))["status"], "active")

    def test_unban_needs_reason_and_restores_access(self):
        admin_post(self.admin, f"users/{self.buyer_id}/ban", kind="permanent", reason="abuse reports")
        self.assertEqual(admin_post(self.admin, f"users/{self.buyer_id}/unban").get_json()["code"], "reason_required")
        self.assertEqual(admin_post(self.admin, f"users/{self.buyer_id}/unban", reason="appeal accepted").status_code, 200)
        self.assertEqual(Peer(self.admin).login("buyer@example.com", PW).status_code, 200)
        self.assertEqual(admin_post(self.admin, f"users/{self.buyer_id}/unban", reason="again again").status_code, 409)
        listed = self.admin.get("/api/v1/admin/users?q=buyer").get_json()["users"][0]
        self.assertEqual(listed["status"], "active")

    def test_lockout_protections(self):
        admin_id = self.db.one("SELECT id FROM users WHERE username = 'admin_001'")["id"]
        self.assertEqual(admin_post(self.admin, f"users/{admin_id}/ban", kind="permanent", reason="test self").get_json()["code"], "self_action")
        other_admin = Peer(self.admin)
        other_admin.signup(email="boss@example.com", pw=PW, name="Boss Admin")
        bid = uid(self.admin, "boss@example.com")
        admin_post(self.admin, f"users/{bid}/role", role="admin")
        other_admin.post("/api/v1/auth/logout", {})
        other_admin.login("boss@example.com", PW)
        r = other_admin.post(f"/api/v1/admin/users/{admin_id}/ban", {"kind": "permanent", "reason": "coup attempt", "password": PW})
        self.assertEqual(r.get_json()["code"], "protected_account")
        for path, body in ((f"users/{admin_id}/status", {"status": "disabled"}), (f"users/{admin_id}/role", {"role": "user"})):
            self.assertEqual(other_admin.post(f"/api/v1/admin/{path}", {**body, "password": PW}).get_json()["code"], "protected_account")
        self.assertEqual(admin_post(self.admin, f"users/{bid}/ban", kind="permanent", reason="not an admin").get_json()["code"], "protected_account")  # demote first

    def test_users_filter_sort_paginate_and_ban_info(self):
        admin_post(self.admin, f"users/{self.buyer_id}/ban", kind="temporary", days=3, reason="suspicious offers")
        r = self.admin.get("/api/v1/admin/users?status=banned").get_json()
        self.assertEqual([u["login"] for u in r["users"]], ["buyer@example.com"])
        self.assertEqual(r["users"][0]["ban"]["reason"], "suspicious offers")
        self.assertEqual(r["users"][0]["ban"]["kind"], "temporary")
        page = self.admin.get("/api/v1/admin/users?per_page=2&page=2&sort=name&dir=asc").get_json()
        self.assertEqual((page["page"], len(page["users"]), page["total"]), (2, 2, 4))
        self.assertEqual(self.admin.get("/api/v1/admin/users?role=admin").get_json()["total"], 1)
        blob = self.admin.get("/api/v1/admin/users").get_data(as_text=True)
        for secret in ("password_hash", "scrypt$", "validator"):
            self.assertNotIn(secret, blob)

    def test_login_events_newest_first_filtered_and_minimal(self):
        Peer(self.admin).login("buyer@example.com", "wrong-password")
        ev = self.admin.get("/api/v1/admin/login-events?per_page=100").get_json()
        stamps = [e["ts"] for e in ev["events"]]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(set(ev["events"][0]), {"ts", "identifier", "method", "success", "reason", "ip_hash"})
        fails = self.admin.get("/api/v1/admin/login-events?outcome=failure&q=buyer").get_json()
        self.assertTrue(fails["events"] and all(e["success"] == 0 for e in fails["events"]))
        self.assertEqual(len(self.admin.get("/api/v1/admin/login-events?per_page=2&page=1").get_json()["events"]), 2)
        self.assertNotIn("127.0.0.1", self.admin.get("/api/v1/admin/login-events").get_data(as_text=True))

    def test_csv_export_is_audited_and_formula_safe(self):
        self.db.execute("UPDATE users SET name = '=HYPERLINK(\"http://x\")' WHERE id = ?", (self.buyer_id,))
        r = self.admin.get("/api/v1/admin/export/users.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["Content-Type"])
        self.assertIn("'=HYPERLINK", r.get_data(as_text=True))
        self.assertNotIn("scrypt", r.get_data(as_text=True))
        self.assertTrue(self.db.one("SELECT 1 AS x FROM audit_log WHERE action = 'csv_export' AND target = 'users'"))
        self.assertEqual(self.admin.get("/api/v1/admin/export/passwords.csv").status_code, 404)
        self.assertTrue(self.admin.get("/api/v1/admin/audit").get_json()["entries"])


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.admin, self.p = world()
        self.db = self.admin.app.extensions["kpt"].database()
        self.listing = self.p["seller"].post("/api/v1/listings", {"title": "3 Bed House", "area": "Gulshan"}).get_json()["listing"]
        r = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": self.listing["id"]})
        self.conv = r.get_json()["conversation"]["id"]

    def send(self, who, text, cid=None, **kw):
        return self.p[who].post(f"/api/v1/messages/conversations/{cid or self.conv}/messages", {"body": text, **kw})

    def test_listing_lookup_hides_the_seller(self):
        r = Peer(self.admin).get(f"/api/v1/listings/by-ref/{self.listing['ref']}").get_json()["listing"]
        self.assertTrue(r["contactable"] and not r["own"])
        self.assertNotIn(uid(self.admin, "seller@example.com"), str(r))
        self.assertTrue(self.p["seller"].get(f"/api/v1/listings/by-ref/{self.listing['ref']}").get_json()["listing"]["own"])
        self.assertEqual(Peer(self.admin).get("/api/v1/listings/by-ref/nope").status_code, 404)

    def test_open_is_idempotent_and_unauthenticated_is_refused(self):
        again = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": self.listing["id"]}).get_json()["conversation"]["id"]
        self.assertEqual(again, self.conv)
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM conversations")["n"], 1)
        self.assertEqual(Peer(self.admin).post("/api/v1/messages/conversations", {"listing_id": self.listing["id"]}).status_code, 401)
        self.assertEqual(self.p["seller"].post("/api/v1/messages/conversations", {"listing_id": self.listing["id"]}).get_json()["code"], "own_listing")
        self.assertEqual(self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": "f" * 32}).status_code, 404)

    def test_order_unread_read_and_sender_comes_from_the_session(self):
        for i in range(3):
            self.assertEqual(self.send("buyer", f"hello {i}").status_code, 201)
        inbox = self.p["seller"].get("/api/v1/messages/conversations").get_json()["conversations"][0]
        self.assertEqual((inbox["unread"], inbox["role"], inbox["counterpart"]), (3, "seller", "Buyer P."))
        self.assertEqual(self.p["seller"].get("/api/v1/messages/unread-count").get_json()["unread"], 3)
        self.p["seller"].post(f"/api/v1/messages/conversations/{self.conv}/read", {})
        self.assertEqual(self.p["seller"].get("/api/v1/messages/unread-count").get_json()["unread"], 0)
        r = self.send("seller", "hi back", sender_id="spoofed", role="admin")  # extra fields are ignored: the sender is the session user
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.p["buyer"].get("/api/v1/messages/unread-count").get_json()["unread"], 1)
        msgs = self.p["buyer"].get(f"/api/v1/messages/conversations/{self.conv}").get_json()["messages"]
        self.assertEqual([m["body"] for m in msgs], ["hello 0", "hello 1", "hello 2", "hi back"])
        self.assertEqual([m["mine"] for m in msgs], [True, True, True, False])

    def test_pagination_and_polling_neither_duplicate_nor_lose(self):
        for i in range(7):
            self.send("buyer", f"m{i}")
        url = f"/api/v1/messages/conversations/{self.conv}"
        newest = self.p["buyer"].get(f"{url}?limit=3").get_json()
        self.assertTrue(newest["has_more"])
        older = self.p["buyer"].get(f"{url}?limit=3&before={newest['messages'][0]['ts']}").get_json()
        oldest = self.p["buyer"].get(f"{url}?limit=3&before={older['messages'][0]['ts']}").get_json()
        got = [m["body"] for m in oldest["messages"] + older["messages"] + newest["messages"]]
        self.assertEqual(got, [f"m{i}" for i in range(7)])
        self.assertFalse(oldest["has_more"])
        self.send("seller", "new one")
        fresh = self.p["buyer"].get(f"{url}?after={newest['messages'][-1]['ts']}").get_json()["messages"]
        self.assertEqual([m["body"] for m in fresh], ["new one"])

    def test_client_id_makes_a_resend_idempotent(self):
        a = self.send("buyer", "once", client_id="abc123").get_json()
        b = self.send("buyer", "once", client_id="abc123").get_json()
        self.assertEqual((a["id"], b["duplicate"]), (b["id"], True))
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM messages")["n"], 1)

    def test_stranger_cannot_touch_the_conversation(self):
        self.send("buyer", "private text")
        base = f"/api/v1/messages/conversations/{self.conv}"
        missing = "/api/v1/messages/conversations/" + "0" * 32
        stranger = self.p["other"]
        for method, suffix, body in (("get", "", None), ("post", "/messages", {"body": "hi"}), ("post", "/read", {}), ("post", "/report", {"reason": "reason here"}),
                                     ("post", "/block", {}), ("post", "/unblock", {})):
            call = (lambda u: stranger.get(u)) if method == "get" else (lambda u, b=body: stranger.post(u, b))
            real, fake = call(base + suffix), call(missing + suffix)
            self.assertEqual((real.status_code, real.get_json()["code"]), (404, "not_found"), suffix)
            self.assertEqual(real.get_json()["error"], fake.get_json()["error"], suffix)  # ids cannot be probed
        self.assertNotIn("private text", stranger.get("/api/v1/messages/conversations").get_data(as_text=True))
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM messages")["n"], 1)

    def test_bodies_are_validated_and_stored_as_plain_text(self):
        self.assertEqual(self.send("buyer", "   ").get_json()["code"], "empty_message")
        self.assertEqual(self.send("buyer", None).status_code, 400)
        self.assertEqual(self.send("buyer", "x" * 2001).get_json()["code"], "message_too_long")
        self.send("buyer", "<img src=x onerror=alert(1)>\x00 hi")
        body = self.p["seller"].get(f"/api/v1/messages/conversations/{self.conv}").get_json()["messages"][-1]["body"]
        self.assertEqual(body, "<img src=x onerror=alert(1)> hi")  # control chars removed; markup kept as inert text for textContent rendering

    def test_csrf_and_rate_limit(self):
        r = self.p["buyer"].post(f"/api/v1/messages/conversations/{self.conv}/messages", {"body": "x"}, token=None)
        self.assertEqual(r.status_code, 403)
        admin, p = world(message_rate_limit_per_min=3)
        lid = p["seller"].post("/api/v1/listings", {"title": "t", "area": "a"}).get_json()["listing"]["id"]
        cid = p["buyer"].post("/api/v1/messages/conversations", {"listing_id": lid}).get_json()["conversation"]["id"]
        codes = [p["buyer"].post(f"/api/v1/messages/conversations/{cid}/messages", {"body": f"s{i}"}).status_code for i in range(5)]
        self.assertEqual(codes[:3], [201, 201, 201])
        self.assertEqual(codes[3], 429)

    def test_block_stops_both_directions_and_unblock_restores(self):
        self.p["seller"].post(f"/api/v1/messages/conversations/{self.conv}/block", {})
        self.assertEqual(self.send("buyer", "hello?").get_json()["code"], "blocked")
        self.assertEqual(self.send("seller", "hello?").get_json()["code"], "blocked")
        self.p["seller"].post(f"/api/v1/messages/conversations/{self.conv}/unblock", {})
        self.assertEqual(self.send("buyer", "hello again").status_code, 201)

    def test_report_can_target_one_message_and_never_one_from_another_conversation(self):
        self.send("buyer", "first line")
        self.send("buyer", "send the deposit to my cousin")
        self.send("seller", "okay")
        hist = self.p["seller"].get(f"/api/v1/messages/conversations/{self.conv}").get_json()["messages"]
        target = next(m for m in hist if m["body"].startswith("send the deposit"))
        url = f"/api/v1/messages/conversations/{self.conv}/report"
        # conversation-level report still works with no message
        whole = self.p["seller"].post(url, {"reason": "pressure to pay early"})
        self.assertEqual(whole.status_code, 201)
        # a message from ANOTHER conversation is rejected, even if the reporter could otherwise know its id
        other_listing = self.p["seller"].post("/api/v1/listings", {"title": "other listing", "area": "a"}).get_json()["listing"]["id"]
        theirs = self.p["other"].post("/api/v1/messages/conversations", {"listing_id": other_listing}).get_json()["conversation"]["id"]
        foreign = self.p["other"].get(f"/api/v1/messages/conversations/{theirs}").get_json()["messages"][0]["id"] if self.send("other", "not part of this chat", cid=theirs).status_code == 201 else None
        self.assertTrue(foreign)
        bad = self.p["seller"].post(url, {"reason": "trying to leak", "message_id": foreign})
        self.assertEqual((bad.status_code, bad.get_json()["code"]), (400, "invalid_message"))
        for junk in ("../x", 5, "0" * 32, "z" * 40):
            self.assertEqual(self.p["seller"].post(url, {"reason": "bad id here", "message_id": junk}).status_code, 400, junk)
        # a participant who is not in this conversation cannot report into it at all
        self.assertEqual(self.p["other"].post(url, {"reason": "outsider report", "message_id": target["id"]}).status_code, 404)
        # selected-message report is stored and surfaces to the admin as the highlighted line only
        picked = self.p["seller"].post(url, {"reason": "this one asks for money", "message_id": target["id"]})
        self.assertEqual(picked.status_code, 201)
        rid = picked.get_json()["report_id"]
        row = self.db.one("SELECT message_id FROM message_reports WHERE id = ?", (rid,))
        self.assertEqual(row["message_id"], target["id"])
        thread = self.admin.get(f"/api/v1/admin/reports/{rid}/thread").get_json()
        self.assertEqual([m["body"] for m in thread["messages"] if m["reported"]], ["send the deposit to my cousin"])
        whole_thread = self.admin.get(f"/api/v1/admin/reports/{whole.get_json()['report_id']}/thread").get_json()
        self.assertFalse(any(m["reported"] for m in whole_thread["messages"]))
        self.assertNotIn("not part of this chat", str(thread))

    def test_report_queue_and_audited_admin_access(self):
        self.send("buyer", "send money to this account")
        self.send("seller", "another private chat line")
        other_listing = self.p["seller"].post("/api/v1/listings", {"title": "t2", "area": "a"}).get_json()["listing"]["id"]
        unreported = self.p["other"].post("/api/v1/messages/conversations", {"listing_id": other_listing}).get_json()["conversation"]["id"]
        self.send("other", "unreported secret", cid=unreported)
        rid = self.p["seller"].post(f"/api/v1/messages/conversations/{self.conv}/report", {"reason": "asks for advance payment"}).get_json()["report_id"]
        queue = self.admin.get("/api/v1/admin/reports").get_json()
        self.assertEqual(queue["total"], 1)
        self.assertNotIn("send money", str(queue))  # the queue never shows message text
        self.assertEqual(self.p["buyer"].get(f"/api/v1/admin/reports/{rid}/thread").status_code, 403)
        thread = self.admin.get(f"/api/v1/admin/reports/{rid}/thread").get_json()
        self.assertEqual([m["from"] for m in thread["messages"]], ["buyer", "seller"])
        self.assertTrue(self.db.one("SELECT 1 AS x FROM audit_log WHERE action = 'report_thread_viewed' AND target = ?", (rid,)))
        self.assertEqual(self.admin.get("/api/v1/admin/reports/" + "0" * 32 + "/thread").status_code, 404)
        self.assertNotIn("unreported secret", str(thread))  # no endpoint browses arbitrary conversations
        self.assertEqual(self.admin.post(f"/api/v1/admin/reports/{rid}/resolve", {"reason": "warned seller"}).status_code, 200)
        self.assertEqual(self.admin.get("/api/v1/admin/reports").get_json()["total"], 0)
        bad = self.p["buyer"].post(f"/api/v1/messages/conversations/{self.conv}/report", {"reason": "bad msg", "message_id": "1" * 32})
        self.assertEqual(bad.get_json()["code"], "invalid_message")

    def test_banned_counterpart_blocks_sends_but_history_stays(self):
        self.send("buyer", "before the ban")
        sid = uid(self.admin, "seller@example.com")
        admin_post(self.admin, f"users/{sid}/ban", kind="permanent", reason="fraud reports")
        self.assertEqual(self.send("buyer", "anyone there?").get_json()["code"], "conversation_closed")
        self.assertEqual(self.p["seller"].get("/api/v1/messages/conversations").status_code, 401)
        self.assertEqual(self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": self.listing["id"]}).get_json()["code"], "listing_unavailable")
        hist = self.p["buyer"].get(f"/api/v1/messages/conversations/{self.conv}").get_json()
        self.assertEqual(hist["messages"][0]["body"], "before the ban")
        self.assertFalse(hist["conversation"]["counterpart_available"])

    def test_account_deletion_keeps_only_reported_conversations(self):
        self.send("buyer", "kept as evidence")
        self.p["seller"].post(f"/api/v1/messages/conversations/{self.conv}/report", {"reason": "harassing me"})
        l2 = self.p["seller"].post("/api/v1/listings", {"title": "t2", "area": "a"}).get_json()["listing"]["id"]
        c2 = self.p["buyer"].post("/api/v1/messages/conversations", {"listing_id": l2}).get_json()["conversation"]["id"]
        self.send("buyer", "delete me", cid=c2)
        r = self.p["buyer"].post("/api/v1/auth/delete-account", {"password": PW, "confirm": "DELETE"})
        self.assertEqual(r.status_code, 200, r.get_json())
        left = [m["body"] for m in self.db.all("SELECT body FROM messages")]
        self.assertEqual(left, ["kept as evidence"])
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM conversations")["n"], 1)

    def test_private_messages_never_reach_ai_code(self):
        from pathlib import Path
        for name in ("services/messaging_service.py", "api/messages.py"):
            src = (Path(__file__).parents[2] / "backend" / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"gemini|openai|chat_service|requests\.|urllib", src, re.I), name)


if __name__ == "__main__":
    unittest.main()
