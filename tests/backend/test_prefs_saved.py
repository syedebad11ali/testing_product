"""G5.2: saved-property favorites through the existing account preferences API (PUT/GET /api/v1/auth/prefs).

Contract pinned here: PUT merges (lists are unioned, so ``prefs`` can only add), ``remove`` takes ids out, a full 30-item list refuses
a new id with 409 saved_limit instead of dropping an old favorite, malformed ids are dropped, and the account is always the session's."""
import unittest
import warnings

warnings.filterwarnings("ignore")

from tests.backend.test_auth import BASE, Client  # noqa: E402

PW = "correct-horse-battery"


class SavedFavoritesApiTests(unittest.TestCase):
    def setUp(self):
        self.cl = Client()
        self.assertEqual(self.cl.signup(email="a@example.com", pw=PW, name="Aisha Khan").status_code, 201)

    def put(self, prefs=None, remove=None, **extra):
        body = {"prefs": {} if prefs is None else prefs, **extra}
        if remove is not None: body["remove"] = remove
        return self.cl.c.put("/api/v1/auth/prefs", json=body, headers={"Origin": BASE, "X-CSRF-Token": self.cl.token}, base_url=BASE)

    def saved(self):
        return self.cl.get("/api/v1/auth/prefs").get_json()["prefs"].get("saved", [])

    def test_add_then_remove(self):
        self.assertEqual(self.put({"saved": ["P1"]}).get_json()["prefs"]["saved"], ["P1"])
        self.assertEqual(self.put({"saved": ["P2"]}).get_json()["prefs"]["saved"], ["P2", "P1"])
        r = self.put(remove={"saved": ["P1"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["prefs"]["saved"], ["P2"])
        self.assertEqual(self.saved(), ["P2"])
        self.assertEqual(self.put(remove={"saved": ["P2"]}).get_json()["prefs"].get("saved"), None)   # empty list is simply absent
        self.assertEqual(self.saved(), [])

    def test_unrelated_preference_fields_survive_add_and_remove(self):
        self.put({"theme": "dark", "lang": "ur", "sort": "newest", "area": "malir", "recent": ["R1"], "compare": ["C1"]})
        self.put({"saved": ["P1", "P2"]})
        after_add = self.cl.get("/api/v1/auth/prefs").get_json()["prefs"]
        self.assertEqual({k: v for k, v in after_add.items() if k != "saved"},
                         {"theme": "dark", "lang": "ur", "sort": "newest", "area": "malir", "recent": ["R1"], "compare": ["C1"]})
        self.put(remove={"saved": ["P1"]})
        after_remove = self.cl.get("/api/v1/auth/prefs").get_json()["prefs"]
        self.assertEqual(after_remove["saved"], ["P2"])
        self.assertEqual({k: v for k, v in after_remove.items() if k != "saved"}, {k: v for k, v in after_add.items() if k != "saved"})

    def test_removing_an_id_that_is_not_saved_is_harmless(self):
        self.put({"saved": ["P1"]})
        self.assertEqual(self.put(remove={"saved": ["NOPE"]}).status_code, 200)
        self.assertEqual(self.saved(), ["P1"])

    def test_two_stale_clients_adding_different_ids_both_persist(self):
        # each sends only its own id: the union keeps both (no client ever sends the whole list back)
        self.put({"saved": ["P1"]}); self.put({"saved": ["P2"]})
        self.assertEqual(sorted(self.saved()), ["P1", "P2"])

    def test_malformed_and_duplicate_ids_are_not_stored(self):
        r = self.put({"saved": ["P1", "P1", "<img src=x>", "../../etc", "", 7, None, "a b"]})
        self.assertEqual(r.get_json()["prefs"]["saved"], ["P1"])
        self.assertEqual(self.put({"saved": ["<script>"]}).get_json()["prefs"]["saved"], ["P1"])

    def test_limit_of_30_is_enforced_without_dropping_a_favorite(self):
        ids = [f"P{i}" for i in range(30)]
        self.put({"saved": ids})
        self.assertEqual(len(self.saved()), 30)
        r = self.put({"saved": ["EXTRA"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["code"], "saved_limit")
        self.assertEqual(sorted(self.saved()), sorted(ids), "nothing was written, nothing evicted")
        self.assertEqual(self.put(remove={"saved": ["P0"]}).status_code, 200)
        self.assertEqual(self.put({"saved": ["EXTRA"]}).status_code, 200)
        self.assertIn("EXTRA", self.saved()); self.assertEqual(len(self.saved()), 30)

    def test_bad_remove_shape_is_rejected(self):
        self.assertEqual(self.put(remove=["P1"]).status_code, 400)
        self.assertEqual(self.put({"saved": ["P1"]}, remove="P1").status_code, 400)

    def test_account_is_the_session_account_and_favorites_are_isolated(self):
        self.put({"saved": ["P1"]})
        # a browser-supplied user id is ignored
        self.put({"saved": ["P9"]}, user_id="someone-else", id="someone-else")
        self.assertEqual(sorted(self.saved()), ["P1", "P9"])
        self.cl.post("/api/v1/auth/logout", {})
        self.assertEqual(self.cl.get("/api/v1/auth/prefs").status_code, 401, "signed out: no favorites at all")
        self.assertEqual(self.cl.signup(email="b@example.com", pw=PW, name="Bilal Ahmed").status_code, 201)
        self.assertEqual(self.saved(), [], "account B does not see account A's favorites")
        self.put({"saved": ["P5"]})
        self.cl.post("/api/v1/auth/logout", {})
        self.assertEqual(self.cl.login("a@example.com", PW).status_code, 200)
        self.assertEqual(sorted(self.saved()), ["P1", "P9"], "account A still has its server-side favorites")
        self.assertNotIn("P5", self.saved())


if __name__ == "__main__":
    unittest.main()
