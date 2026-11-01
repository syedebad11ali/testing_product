"""G5.3c: home filters (area, ptype, sort) stored per account through the existing preferences API (PUT/GET /api/v1/auth/prefs).

The sanitizer already accepted the three fields; the only gap was that a scalar can be overwritten but never unset by the merge, so
"All areas" could not be stored. ``remove.fields`` clears them. Everything else (the G5.2 ``saved`` list and ``remove.saved``, theme,
language, the other lists) must stay exactly as it was, and each account only ever sees its own values."""
import unittest
import warnings

warnings.filterwarnings("ignore")

from backend.services import prefs as prefs_mod  # noqa: E402
from tests.backend.test_auth import BASE, Client  # noqa: E402

PW = "correct-horse-battery"
OTHERS = {"theme": "dark", "lang": "ur", "recent": ["R1"], "compare": ["C1"], "saved": ["P1", "P2"], "dismissed": ["intro"], "min_price": 5000000}


class ApplyUpdateFilterTests(unittest.TestCase):
    def test_clear_fields_removes_only_the_named_filters(self):
        account = {**OTHERS, "area": "malir", "ptype": "house", "sort": "price_asc"}
        final, evicted = prefs_mod.apply_update(account, {}, {"fields": ["area", "sort"]})
        self.assertEqual(final, {**OTHERS, "ptype": "house"})
        self.assertEqual(evicted, [])

    def test_only_the_home_filters_can_be_cleared(self):
        account = {**OTHERS, "area": "malir"}
        final, _ = prefs_mod.apply_update(account, {}, {"fields": ["theme", "lang", "saved", "recent", "min_price", "nope", 7, None, {"x": 1}]})
        self.assertEqual(final, account, "theme, language, lists and unknown keys cannot be removed this way")
        self.assertEqual(prefs_mod.apply_update(account, {}, {"fields": "area"})[0], account, "not a list: ignored")
        self.assertEqual(prefs_mod.apply_update(account, {}, {"fields": None})[0], account)

    def test_setting_and_clearing_in_one_update_and_saved_removal_together(self):
        account = {**OTHERS, "area": "malir", "ptype": "house"}
        final, evicted = prefs_mod.apply_update(account, {"sort": "price_desc", "area": "dha phase 6"},
                                                {"fields": ["ptype"], "saved": ["P1"]})
        self.assertEqual(final["area"], "dha phase 6"); self.assertEqual(final["sort"], "price_desc")
        self.assertNotIn("ptype", final)
        self.assertEqual(final["saved"], ["P2"], "G5.2 remove.saved still works in the same call")
        self.assertEqual(evicted, [])

    def test_a_plain_update_never_clears_a_filter(self):
        account = {"area": "malir", "sort": "newest"}
        self.assertEqual(prefs_mod.apply_update(account, {"theme": "dark"})[0], {"area": "malir", "sort": "newest", "theme": "dark"})
        self.assertEqual(prefs_mod.apply_update(account, {"area": None, "sort": "bogus"})[0], account, "null / invalid values are dropped, not stored and not clearing")


class FilterApiTests(unittest.TestCase):
    def setUp(self):
        self.a = Client()
        self.assertEqual(self.a.signup(email="a@example.com", pw=PW, name="Aisha Khan").status_code, 201)
        # a second browser (own cookie jar) on the same app: account B
        self.bc = self.a.app.test_client()
        self.b_token = self.bc.get("/api/v1/auth/csrf", base_url=BASE).get_json()["csrf_token"]
        r = self.bc.post("/api/v1/auth/signup", json={"name": "Bilal Ahmed", "email": "b@example.com", "password": PW},
                         headers={"Origin": BASE, "X-CSRF-Token": self.b_token}, base_url=BASE)
        self.assertEqual(r.status_code, 201)

    def put_a(self, prefs=None, remove=None):
        body = {"prefs": {} if prefs is None else prefs}
        if remove is not None: body["remove"] = remove
        return self.a.c.put("/api/v1/auth/prefs", json=body, headers={"Origin": BASE, "X-CSRF-Token": self.a.token}, base_url=BASE)

    def put_b(self, prefs=None, remove=None, **extra):
        body = {"prefs": {} if prefs is None else prefs, **extra}
        if remove is not None: body["remove"] = remove
        return self.bc.put("/api/v1/auth/prefs", json=body, headers={"Origin": BASE, "X-CSRF-Token": self.b_token}, base_url=BASE)

    def get_a(self): return self.a.get("/api/v1/auth/prefs").get_json()["prefs"]
    def get_b(self): return self.bc.get("/api/v1/auth/prefs", base_url=BASE).get_json()["prefs"]

    def test_filters_are_stored_loaded_and_cleared_through_the_api(self):
        r = self.put_a({"area": "DHA Phase 6", "ptype": "House", "sort": "price_desc"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get_a(), {"area": "dha phase 6", "ptype": "house", "sort": "price_desc"})
        r = self.put_a({}, {"fields": ["area", "ptype", "sort"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get_a(), {})

    def test_account_a_and_b_have_separate_filters(self):
        self.put_a({"area": "malir", "sort": "price_asc"})
        self.assertEqual(self.get_b(), {}, "B does not see A's filters")
        self.put_b({"area": "gulshan-e-iqbal", "ptype": "plot"})
        self.assertEqual(self.get_a(), {"area": "malir", "sort": "price_asc"})
        self.assertEqual(self.get_b(), {"area": "gulshan-e-iqbal", "ptype": "plot"})
        self.put_b({}, {"fields": ["area", "ptype", "sort"]})
        self.assertEqual(self.get_a(), {"area": "malir", "sort": "price_asc"}, "B clearing its filters does not touch A")

    def test_a_user_id_in_the_request_is_ignored(self):
        self.put_b({"area": "malir"}, user_id="whoever", id="x")
        self.put_a({"area": "bahria town"})
        self.put_a({"area": "x"}, {"fields": ["area"], "user_id": "b"})
        self.assertEqual(self.get_b(), {"area": "malir"}, "A's requests never reach B")
        self.assertEqual(self.get_a(), {})

    def test_favorites_and_other_fields_survive_filter_updates(self):
        self.put_a({k: v for k, v in OTHERS.items()})
        self.put_a({"area": "malir", "ptype": "house", "sort": "newest"})
        after = self.get_a()
        self.assertEqual({k: v for k, v in after.items() if k in OTHERS}, OTHERS)
        self.put_a({"area": "dha phase 6"}, {"fields": ["ptype", "sort"]})
        after = self.get_a()
        self.assertEqual(after, {**OTHERS, "area": "dha phase 6"})
        # G5.2 behavior intact on the same account
        self.assertEqual(self.put_a({}, {"saved": ["P1"]}).get_json()["prefs"]["saved"], ["P2"])
        self.assertEqual(self.get_a()["area"], "dha phase 6")
        self.assertEqual(self.put_a({"saved": ["P9"]}).get_json()["prefs"]["saved"], ["P9", "P2"])

    def test_invalid_filter_values_are_dropped_and_clearing_junk_is_harmless(self):
        r = self.put_a({"area": "<img src=x>", "ptype": 5, "sort": "DROP TABLE"})
        self.assertEqual((r.status_code, r.get_json()["prefs"]), (200, {}))
        self.put_a({"area": "malir"})
        self.assertEqual(self.put_a({}, {"fields": [1, None, "theme", "area", "area"]}).status_code, 200)
        self.assertEqual(self.get_a(), {})
        self.assertEqual(self.put_a({}, {"fields": "area"}).status_code, 200)
        self.assertEqual(self.a.c.put("/api/v1/auth/prefs", json={"prefs": {}, "remove": [1]}, headers={"Origin": BASE, "X-CSRF-Token": self.a.token}, base_url=BASE).status_code, 400)

    def test_signed_out_requests_are_refused(self):
        anon = Client()
        self.assertEqual(anon.get("/api/v1/auth/prefs").status_code, 401)
        r = anon.c.put("/api/v1/auth/prefs", json={"prefs": {"area": "malir"}}, headers={"Origin": BASE, "X-CSRF-Token": anon.token}, base_url=BASE)
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
